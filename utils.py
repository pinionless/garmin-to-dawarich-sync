# ========================================================
# = utils.py - Utility functions and context processors
# ========================================================
from flask import current_app, flash
import os
import datetime
import mimetypes
import requests
from bs4 import BeautifulSoup
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garth.exc import GarthHTTPError
from models import db, DownloadRecord, UserSettings
import hashlib, base64
import time # Added for sleep functionality

def run_custom_check(app, stop_event):
    """
    Runs a custom check for activities in a date range, day by day, with a delay.
    This function is designed to be run in a background thread.
    """
    with app.app_context():
        task_info = app.config['CUSTOM_CHECK_TASK']
        task_info['status_message'] = "Starting custom check..."
        app.logger.info("Background custom check thread started.")
        settings = UserSettings.query.first()
        
        if not all([settings, settings.manual_check_start_date, settings.manual_check_end_date, settings.manual_check_delay_seconds is not None]):
            app.logger.error("Custom check thread exiting: Invalid settings.")
            task_info['status_message'] = "Custom check failed: Invalid settings."
            return

        current_date = settings.manual_check_start_date
        end_date = settings.manual_check_end_date
        delay = settings.manual_check_delay_seconds

        while current_date <= end_date:
            if stop_event.is_set():
                app.logger.info(f"Custom check stop signal received. Stopping before processing {current_date.isoformat()}.")
                task_info['status_message'] = "Custom check stopped by user."
                break

            status_msg = f"Processing date {current_date.isoformat()}..."
            task_info['status_message'] = status_msg
            app.logger.info(f"Custom check: {status_msg}")
            
            start_of_day = datetime.datetime.combine(current_date, datetime.time.min)
            end_of_day = datetime.datetime.combine(current_date, datetime.time.max)

            try:
                count = download_activities(start_of_day, end_of_day)
                app.logger.info(f"Custom check: Downloaded {count} activities for {current_date.isoformat()}.")
                
                # Update start date for the next run
                settings.manual_check_start_date = current_date + datetime.timedelta(days=1)
                db.session.commit()
                app.logger.info(f"Custom check: Updated start date to {settings.manual_check_start_date.isoformat()}.")

            except Exception as e:
                error_msg = f"Custom check failed on {current_date.isoformat()}: {e}"
                task_info['status_message'] = error_msg
                app.logger.error(error_msg, exc_info=True)
                app.logger.error("Custom check: Aborting due to error.")
                break
            
            # Move to the next day
            current_date += datetime.timedelta(days=1)

            # If there are more days to process, wait
            if current_date <= end_date and not stop_event.is_set():
                wait_msg = f"Waiting for {delay} seconds before processing next day."
                task_info['status_message'] = wait_msg
                app.logger.info(f"Custom check: {wait_msg}")
                time.sleep(delay)

        if not stop_event.is_set():
            task_info['status_message'] = "Custom check finished successfully."
        app.logger.info("Background custom check thread finished.")
        # Clean up the task info in the app config
        app.config['CUSTOM_CHECK_TASK']['thread'] = None
        app.config['CUSTOM_CHECK_TASK']['stop_event'] = None


def check_dawarich_connection(force_check=False):
    """
    Checks connection and login to Dawarich. Caches the result for 5 minutes.
    Flashes an error message on failure.
    """
    status_cache = current_app.config['_DAWARICH_CONNECTION_STATUS']
    # Use cached status if available and not forced, and younger than 5 minutes
    if not force_check and status_cache.get('timestamp'):
        if (time.time() - status_cache['timestamp']) < 900: # 5 minutes
            if not status_cache['status']:
                flash(status_cache['message'], 'error')
            return status_cache['status']

    host = current_app.config.get('DAWARICH_HOST')
    user = current_app.config.get('DAWARICH_EMAIL')
    pwd = current_app.config.get('DAWARICH_PASSWORD')

    if not all([host, user, pwd]):
        msg = "Dawarich connection failed: Host, email, or password not configured."
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False

    login_url = f'{host}/users/sign_in'
    sess = requests.Session()

    try:
        page = sess.get(login_url, timeout=10)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
        token_element = soup.find('input', {'name': 'authenticity_token'})
        if not token_element:
            raise ValueError("Could not find CSRF token on Dawarich login page.")
        token = token_element['value']

        data = {
            'user[email]': user,
            'user[password]': pwd,
            'authenticity_token': token
        }
        resp = sess.post(login_url, data=data, timeout=10)
        resp.raise_for_status()

        if "Invalid Email or password." in resp.text:
            raise ValueError("Invalid Dawarich credentials.")

        # --- Find Dawarich Version ---
        soup_dashboard = BeautifulSoup(resp.text, 'html.parser')
        version_link = soup_dashboard.find('a', href="https://github.com/Freika/dawarich/releases/latest")
        dawarich_version = None
        if version_link:
            version_span = version_link.find('span')
            if version_span:
                dawarich_version = version_span.text.strip()

        settings = UserSettings.query.first()
        if settings and settings.ignore_safe_dawarich_versions:
            current_app.logger.warning("Dawarich safe version check is being ignored by user setting.")
        else:
            safe_versions = current_app.config.get('SAFE_VERSIONS', [])
            if not dawarich_version:
                msg = "Could not determine Dawarich version. Aborting as a precaution."
                current_app.logger.error(msg)
                flash(msg, 'error')
                status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
                return False

            if dawarich_version not in safe_versions:
                msg = f"Dawarich version {dawarich_version} is not in the list of safe versions: {safe_versions}"
                current_app.logger.error(msg)
                flash(msg, 'error')
                status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': dawarich_version})
                return False

        current_app.logger.info(f"Dawarich connection check successful. Version: {dawarich_version}")
        status_cache.update({'status': True, 'timestamp': time.time(), 'message': '', 'version': dawarich_version})
        return True

    except requests.exceptions.RequestException as e:
        msg = f"Dawarich connection failed: Network error - {e}"
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False
    except ValueError as e:
        msg = f"Dawarich connection failed: {e}"
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False
    except Exception as e:
        msg = f"Dawarich connection failed: An unexpected error occurred - {e}"
        current_app.logger.error(msg, exc_info=True)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False

def scheduled_download_job(app_instance):
    """Job to be run by the scheduler. Downloads activities from yesterday and then uploads them."""
    with app_instance.app_context():
        # --- Download Phase ---
        try:
            app_instance.logger.info("Scheduler: Starting scheduled download job.")
            today     = datetime.datetime.now().date()
            yesterday = today - datetime.timedelta(days=1)
            start     = datetime.datetime.combine(yesterday, datetime.time())
            end       = datetime.datetime.combine(yesterday, datetime.time.max)

            download_count = download_activities(start, end) # download_activities is already in this file
            app_instance.logger.info(f"Scheduler: Downloaded {download_count} GPX files.")
        except Exception as e:
            app_instance.logger.error(f"Scheduler: Error during scheduled download phase: {e}", exc_info=True)
            # Optionally, decide if you want to proceed to upload phase if download fails
            # For now, we'll let it proceed to attempt uploading any previously downloaded files.

        # --- Upload Phase ---
        app_instance.logger.info("Scheduler: Starting scheduled upload job.")
        uploaded_count = 0
        failed_count = 0
        
        # Retrieve GPX_FILES_DIR from config, defaulting if not set
        gpx_base_path = '/garmin/activities/'

        # Find all records that haven't been uploaded to Dawarich
        records_to_upload = DownloadRecord.query.filter(
            (DownloadRecord.dawarich == False) | (DownloadRecord.dawarich == None)
        ).order_by(DownloadRecord.id.asc()).all()

        if not records_to_upload:
            app_instance.logger.info("Scheduler: No new files to upload to Dawarich.")
            return

        app_instance.logger.info(f"Scheduler: Found {len(records_to_upload)} file(s) to attempt uploading.")

        for record in records_to_upload:
            filename = record.filename
            gpx_file_path = os.path.join(gpx_base_path, filename)

            app_instance.logger.info(f"Scheduler: Attempting to upload {filename} (path: {gpx_file_path})")

            if not os.path.exists(gpx_file_path):
                app_instance.logger.error(f"Scheduler: File {gpx_file_path} not found for record ID {record.id}. Skipping.")
                # Optionally, mark as failed or handle differently in the DB
                failed_count +=1
                continue

            try:
                success = submit_location_data(gpx_file_path)
                
                if success:
                    record.dawarich = True
                    db.session.commit()
                    app_instance.logger.info(f"Scheduler: Successfully uploaded {filename} and updated database record ID {record.id}.")
                    uploaded_count += 1
                else:
                    # This case might be hit if submit_location_data returns False for non-critical issues.
                    app_instance.logger.warning(f"Scheduler: Upload of {filename} reported non-success by submit_location_data.")
                    failed_count += 1
            
            except Exception as e:
                db.session.rollback() 
                app_instance.logger.error(f"Scheduler: Failed to upload {filename}: {e}", exc_info=True)
                failed_count += 1
            
            finally:
                # Delay before processing the next file, if there are more files
                if record != records_to_upload[-1]: # Check if it's not the last record
                    app_instance.logger.info(f"Scheduler: Waiting 5 seconds before next upload...")
                    time.sleep(5)
        
        app_instance.logger.info(f"Scheduler: Upload job finished. Successfully uploaded: {uploaded_count}, Failed/Skipped: {failed_count}.")


def init_garmin():
    ts = '/garmin/.garminconnect'
    b64 = '/garmin/.garminconnect_base64'
    tokenstore = os.path.expanduser(ts)
    tokenstore_b64 = os.path.expanduser(b64)

    email = current_app.config.get('GARMIN_EMAIL')
    pwd   = current_app.config.get('GARMIN_PASSWORD')
    try:
        gc = Garmin()
        gc.login(tokenstore)
    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        if not email or not pwd:
            raise ValueError("Missing credentials and no token cache")
        gc = Garmin(email=email, password=pwd, return_on_mfa=True)
        result = gc.login()
        if isinstance(result, tuple) and result[0] == "needs_mfa":
            raise RuntimeError("MFA required – pre‐populate tokens")
        gc.garth.dump(tokenstore)
        with open(tokenstore_b64, "w") as f:
            f.write(gc.garth.dumps())
        gc.login(tokenstore)
    return gc

def download_activities(startdate: datetime.datetime,
                        enddate:   datetime.datetime) -> int:
    save_to = "/garmin/activities"
    os.makedirs(save_to, exist_ok=True)
    gc = init_garmin()
    activities = gc.get_activities_by_date(
        startdate.isoformat(), enddate.isoformat()
    )
    
    exclusions = current_app.config.get('EXCLUDE', [])
    saved = 0

    for act in activities:
        name = act.get("activityName", "")
        if name in exclusions:
            current_app.logger.info(f"Skipping excluded activity: {name}")
            continue

        act_id   = act["activityId"]
        act_date = datetime.datetime.strptime(
            act["startTimeLocal"], "%Y-%m-%d %H:%M:%S"
        ).strftime("%Y-%m-%d")
        filename = f"{act_date}_{act_id}.gpx"

        if DownloadRecord.query.filter_by(filename=filename).first():
            current_app.logger.info(f"Already downloaded, skipping: {filename}")
            continue

        data = gc.download_activity(
            act_id,
            dl_fmt=gc.ActivityDownloadFormat.GPX
        )

        # Parse the GPX data and check for trackpoints
        soup = BeautifulSoup(data, 'xml')
        if not soup.find('trkpt'):
            current_app.logger.info(f"Skipping activity {act_id} ('{name}') as it contains no location data.")
            continue

        path = os.path.join(save_to, filename)
        with open(path, "wb") as fb:
            fb.write(data)

        record = DownloadRecord(filename=filename)
        db.session.add(record)
        db.session.commit()
        saved += 1

    return saved



def submit_location_data(gpx_path: str, source: str = "gpx") -> bool:
    """
    1) Log in and get CSRF token
    2) Fetch the import form to get the direct-upload URL and import CSRF token
    3) Direct-upload the GPX file blob metadata
    4) Upload the actual GPX file
    5) Submit the import form with the signed_id of the uploaded blob
    """
    if not check_dawarich_connection():
        current_app.logger.error("submit_location_data: Aborting due to failed Dawarich connection check.")
        return False

    current_app.logger.info(f"submit_location_data: Starting import for {gpx_path}, source={source}")
    # -- 1) LOGIN ---------------------------------------------------------
    host  = current_app.config.get('DAWARICH_HOST')
    login_url =f'{host}/users/sign_in'

    user = current_app.config.get('DAWARICH_EMAIL') 
    pwd  = current_app.config.get('DAWARICH_PASSWORD')

    sess = requests.Session()
    # first GET login page to retrieve CSRF token
    page = sess.get(login_url)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, 'html.parser')
    token = soup.find('input', {'name': 'authenticity_token'})['value']
    current_app.logger.debug(f"submit_location_data: Step 1: Fetched login CSRF token={token[:8]}…")

    # now POST credentials + token
    data = {
        'user[email]': user,
        'user[password]': pwd,
        'authenticity_token': token
    }
    current_app.logger.debug(f"submit_location_data: Step 1: POSTing login credentials to {login_url}")
    resp = sess.post(login_url, data=data)
    resp.raise_for_status()
    current_app.logger.info(f"submit_location_data: Step 1: Login successful to {login_url}")
    current_app.logger.debug(f"submit_location_data: Step 1: Session cookies after login: {sess.cookies.get_dict()}")

    # -- 2) IMPORT FORM ---------------------------------------------------
    form_url = f'{host}/imports/new'
    resp = sess.get(form_url); resp.raise_for_status()
    current_app.logger.debug(f"submit_location_data: Step 2: GET import form {form_url} status={resp.status_code}")
    soup2 = BeautifulSoup(resp.text, 'html.parser')

    # Try to get CSRF token from meta tag first, then fall back to input field
    import_csrf_meta_tag = soup2.find('meta', {'name': 'csrf-token'})
    if import_csrf_meta_tag and import_csrf_meta_tag.get('content'):
        import_token = import_csrf_meta_tag['content']
        current_app.logger.debug("submit_location_data: Step 2: Extracted import CSRF token from meta tag.")
    else:
        import_token_element = soup2.find('input', {'name':'authenticity_token'})
        if not import_token_element:
            current_app.logger.error("submit_location_data: Step 2: Could not find authenticity_token (meta or input) on import page.")
            raise RuntimeError("Could not find authenticity_token (meta or input) on import page.")
        import_token = import_token_element['value']
        current_app.logger.debug("submit_location_data: Step 2: Extracted import CSRF token from input field.")

    direct_upload_url = soup2.find(
        'form', {'data-controller':'direct-upload'}
    )['data-direct-upload-url-value']
    current_app.logger.info(f"submit_location_data: Step 2: Import CSRF token={import_token[:8]}…, Direct-upload URL={direct_upload_url}")

    # -- 3) DIRECT UPLOAD BLOB META ---------------------------------------
    filename     = os.path.basename(gpx_path)
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # load file bytes for size & checksum
    with open(gpx_path, 'rb') as f:
        file_data = f.read()
    byte_size = len(file_data)
    checksum  = base64.b64encode(hashlib.md5(file_data).digest()).decode()
    blob_json = {
        'blob': {
            'filename': filename,
            'content_type': content_type,
            'byte_size': byte_size,
            'checksum':  checksum
        }
    }

    # Derive Origin and Referer from form_url for headers
    parsed_form_url_step3 = requests.utils.urlparse(form_url)
    origin_step3 = f"{parsed_form_url_step3.scheme}://{parsed_form_url_step3.netloc}"

    headers_step3 = {
        'Content-Type': 'application/json',
        'Accept':       'application/json',
        'X-CSRF-Token': import_token, # Use the token from the import form
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': form_url,
        'Origin': origin_step3,
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0'
    }
    current_app.logger.debug(f"submit_location_data: Step 3: Blob metadata payload: {blob_json}")
    current_app.logger.debug(f"submit_location_data: Step 3: Headers for blob metadata POST: {headers_step3}")
    current_app.logger.debug(f"submit_location_data: Step 3: POSTing blob metadata to {direct_upload_url}")
    r = sess.post(direct_upload_url, json=blob_json, headers=headers_step3)
    if not r.ok:
        current_app.logger.error(
            f"submit_location_data: Step 3: Direct-upload metadata POST failed: {r.status_code} - {r.text[:500]}"
        )
    r.raise_for_status()
    info      = r.json()
    signed_id = info['signed_id']
    current_app.logger.info(f"submit_location_data: Step 3: Direct-upload metadata POST successful. Signed ID: {signed_id[:15]}…")
    current_app.logger.debug(f"submit_location_data: Step 3: Full direct upload info: {info}")


    # -- 4) UPLOAD ACTUAL FILE --------------------------------------------
    upload_url = info['direct_upload']['url']
    upload_headers = info['direct_upload']['headers']

    current_app.logger.debug(f"submit_location_data: Step 4: Uploading file to {upload_url}")
    current_app.logger.debug(f"submit_location_data: Step 4: Headers for file PUT: {upload_headers}")
    with open(gpx_path, 'rb') as f:
        r = sess.put(upload_url, data=f, headers=upload_headers)
    if not r.ok:
        current_app.logger.error(
            f"submit_location_data: Step 4: File PUT failed: {r.status_code} - {r.text[:500]}"
        )
    r.raise_for_status()
    current_app.logger.info(f"submit_location_data: Step 4: File PUT to {upload_url} successful.")

    # -- 5) SUBMIT IMPORT -------------------------------------------------
    import_url = f'{host}/imports'
    form_data_step5 = [
        ('authenticity_token', import_token), # This is the CSRF token for the form
        ('import[source]',     source),
        ('import[files][]',    signed_id)
    ]

    origin_step5 = origin_step3
    
    headers_step5 = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Referer': form_url, 
        'Origin': origin_step5,
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0'
    }
    
    current_app.logger.debug(f"submit_location_data: Step 5: Form data for final import: {form_data_step5}")
    current_app.logger.debug(f"submit_location_data: Step 5: Headers for final import POST: {headers_step5}")
    current_app.logger.debug(f"submit_location_data: Step 5: POSTing final import form to {import_url}")
    # Add files={} to ensure Content-Type is multipart/form-data, matching browser behavior for forms with enctype="multipart/form-data"
    resp = sess.post(import_url, data=form_data_step5, headers=headers_step5, files={}) 
    
    if not resp.ok:
        current_app.logger.error(
            f"submit_location_data: Step 5: Final import POST failed: {resp.status_code} - {resp.text[:500]}"
        )
    resp.raise_for_status()
    current_app.logger.info(f"submit_location_data: Step 5: Final import POST to {import_url} successful (status={resp.status_code}).")

    current_app.logger.info(f"submit_location_data: Successfully imported {filename} (blob signed_id: {signed_id[:15]}…).")
    return True