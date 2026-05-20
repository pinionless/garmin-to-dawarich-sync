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
    HTTPError,
)
from models import db, DownloadRecord, UserSettings
import time # Added for sleep functionality
import shutil

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
    Checks connection and login to Dawarich. Caches the result for 2 minutes.
    Flashes an error message on failure.
    """
    status_cache = current_app.config['_DAWARICH_CONNECTION_STATUS']
    # Use cached status if available and not forced, and younger than 2 minutes
    if not force_check and status_cache.get('timestamp'):
        if (time.time() - status_cache['timestamp']) < 120: # 2 minutes
            if not status_cache['status']:
                flash(status_cache['message'], 'error')
            return status_cache['status']

    host = (current_app.config.get('DAWARICH_HOST') or '').rstrip('/')
    api_key = current_app.config.get('DAWARICH_API_KEY')

    if not host:
        msg = "Dawarich connection failed: Host not configured."
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False

    if not api_key:
        msg = "Dawarich connection failed: DAWARICH_API_KEY is required for Dawarich 1.3.4 API upload."
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False

    imports_url = f'{host}/api/v1/imports'
    try:
        resp = requests.get(
            imports_url,
            params={'api_key': api_key, 'per_page': 1},
            timeout=10,
        )
        resp.raise_for_status()
        current_app.logger.info("Dawarich API connection check successful.")
        status_cache.update({'status': True, 'timestamp': time.time(), 'message': '', 'version': '1.3.4+'})
        return True
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code == 404:
            msg = (
                "Dawarich API import endpoint not found. DAWARICH_API_KEY upload requires "
                "Dawarich 1.3.4 with the /api/v1/imports endpoint."
            )
        elif status_code in (401, 403):
            msg = "Dawarich API connection failed: invalid API key or API access denied."
        else:
            msg = f"Dawarich API connection failed: HTTP error - {e}"
        current_app.logger.error(msg)
        flash(msg, 'error')
        status_cache.update({'status': False, 'timestamp': time.time(), 'message': msg, 'version': None})
        return False
    except requests.exceptions.RequestException as e:
        msg = f"Dawarich API connection failed: Network error - {e}"
        current_app.logger.error(msg)
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


GARMIN_TOKENSTORE = '/garmin/.garminconnect'
GARMIN_TOKENSTORE_B64 = '/garmin/.garminconnect_base64'


def get_garmin_login_status():
    """Check whether valid Garmin tokens exist.

    Returns a dict with:
        logged_in (bool): True if tokens exist and can be loaded
        display_name (str|None): The Garmin display name if available
    """
    tokenstore = GARMIN_TOKENSTORE
    try:
        gc = Garmin()
        gc.login(tokenstore)
        name = gc.display_name or gc.full_name or "Garmin User"
        return {"logged_in": True, "display_name": name}
    except Exception:
        return {"logged_in": False, "display_name": None}


def garmin_interactive_login(email, password):
    """Begin an interactive Garmin login from the web UI.

    Returns a dict with:
        status: "success" | "needs_mfa" | "error"
        message: Human-readable message
    On "needs_mfa", the MFA client state is stored in app.config
    so that garmin_complete_mfa() can finish the flow.
    """
    tokenstore = GARMIN_TOKENSTORE
    try:
        gc = Garmin(email=email, password=password, return_on_mfa=True)
        result = gc.login()

        if isinstance(result, tuple) and result[0] == "needs_mfa":
            # Stash the Garmin client + MFA state for the next step
            current_app.config['_GARMIN_MFA_STATE'] = {
                'gc': gc,
                'client_state': result[1],
            }
            return {
                "status": "needs_mfa",
                "message": "MFA code required. Check your authenticator app or SMS."
            }

        # No MFA needed — save tokens
        gc.client.dump(tokenstore)
        with open(GARMIN_TOKENSTORE_B64, "w") as f:
            f.write(gc.client.dumps())
        current_app.logger.info("Garmin interactive login successful (no MFA).")
        return {
            "status": "success",
            "message": "Logged in to Garmin Connect successfully.",
            "display_name": gc.display_name or gc.full_name or "Garmin User",
        }

    except GarminConnectAuthenticationError as e:
        current_app.logger.warning(f"Garmin interactive login auth error: {e}")
        return {"status": "error", "message": "Invalid email or password."}
    except GarminConnectTooManyRequestsError as e:
        current_app.logger.warning(f"Garmin interactive login rate-limited: {e}")
        return {"status": "error", "message": "Too many login attempts. Please wait a few minutes and try again."}
    except Exception as e:
        current_app.logger.error(f"Garmin interactive login failed: {e}", exc_info=True)
        return {"status": "error", "message": f"Login failed: {e}"}


def garmin_complete_mfa(mfa_code):
    """Complete an MFA challenge started by garmin_interactive_login().

    Returns a dict with:
        status: "success" | "error"
        message: Human-readable message
    """
    tokenstore = GARMIN_TOKENSTORE
    mfa_state = current_app.config.get('_GARMIN_MFA_STATE')

    if not mfa_state:
        return {"status": "error", "message": "No pending MFA session. Please start the login again."}

    gc = mfa_state['gc']
    client_state = mfa_state['client_state']

    try:
        gc.resume_login(client_state, mfa_code)

        # Save tokens
        gc.client.dump(tokenstore)
        with open(GARMIN_TOKENSTORE_B64, "w") as f:
            f.write(gc.client.dumps())

        # Clear MFA state
        current_app.config.pop('_GARMIN_MFA_STATE', None)

        current_app.logger.info("Garmin MFA login completed successfully.")
        return {
            "status": "success",
            "message": "Logged in to Garmin Connect successfully.",
            "display_name": gc.display_name or gc.full_name or "Garmin User",
        }

    except HTTPError as e:
        error_str = str(e)
        if "429" in error_str:
            current_app.config.pop('_GARMIN_MFA_STATE', None)
            return {"status": "error", "message": "Too many attempts. Please wait and start login again."}
        elif "401" in error_str or "403" in error_str:
            return {"status": "error", "message": "Invalid MFA code. Please try again."}
        else:
            current_app.config.pop('_GARMIN_MFA_STATE', None)
            current_app.logger.error(f"Garmin MFA failed: {e}", exc_info=True)
            return {"status": "error", "message": f"MFA verification failed: {e}"}
    except Exception as e:
        current_app.config.pop('_GARMIN_MFA_STATE', None)
        current_app.logger.error(f"Garmin MFA failed: {e}", exc_info=True)
        return {"status": "error", "message": f"MFA verification failed: {e}"}


def garmin_logout():
    """Remove stored Garmin tokens."""
    tokenstore = GARMIN_TOKENSTORE
    b64_file = GARMIN_TOKENSTORE_B64
    removed = False

    if os.path.isdir(tokenstore):
        shutil.rmtree(tokenstore, ignore_errors=True)
        removed = True
    if os.path.isfile(b64_file):
        os.remove(b64_file)
        removed = True

    # Clear any pending MFA state
    current_app.config.pop('_GARMIN_MFA_STATE', None)

    if removed:
        current_app.logger.info("Garmin tokens removed (logged out).")
        return {"status": "success", "message": "Logged out of Garmin Connect."}
    else:
        return {"status": "success", "message": "Already logged out (no tokens found)."}


def init_garmin():
    """Initialise and return an authenticated Garmin client.

    Attempts token-based login first, then falls back to env-var
    credentials.  If MFA is required the user is directed to use the
    interactive login in the web UI.
    """
    tokenstore = GARMIN_TOKENSTORE

    email = current_app.config.get('GARMIN_EMAIL')
    pwd   = current_app.config.get('GARMIN_PASSWORD')

    # 1. Try cached tokens
    try:
        gc = Garmin()
        gc.login(tokenstore)
        return gc
    except (FileNotFoundError, HTTPError, GarminConnectAuthenticationError):
        pass  # Fall through to credential login

    # 2. Try env-var credentials
    if not email or not pwd:
        raise ValueError(
            "No cached Garmin session and no GARMIN_EMAIL/GARMIN_PASSWORD configured. "
            "Please log in via the Settings page in the web UI."
        )

    try:
        gc = Garmin(email=email, password=pwd, return_on_mfa=True)
        result = gc.login()
        if isinstance(result, tuple) and result[0] == "needs_mfa":
            raise RuntimeError(
                "MFA is required for this Garmin account. "
                "Please log in via the Settings page in the web UI."
            )
        gc.client.dump(tokenstore)
        with open(GARMIN_TOKENSTORE_B64, "w") as f:
            f.write(gc.client.dumps())
        gc.login(tokenstore)
    except (RuntimeError, ValueError):
        raise
    except Exception as e:
        raise ValueError(f"Garmin credential login failed: {e}") from e

    return gc

def download_activities(startdate: datetime.datetime,
                        enddate:   datetime.datetime) -> int:
    save_to = "/garmin/activities"
    os.makedirs(save_to, exist_ok=True)
    gc = init_garmin()
    activities = gc.get_activities_by_date(
        startdate.strftime("%Y-%m-%d"), enddate.strftime("%Y-%m-%d")
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
        # The 'xml' parser requires a library like 'lxml' to be installed.
        soup = BeautifulSoup(data, 'lxml-xml')
        if not soup.find('trkpt'):
            current_app.logger.info(f"Skipping activity {act_id} ('{name}') as it contains no location data.")
            continue

        path = os.path.join(save_to, filename)
        with open(path, "wb") as fb:
            fb.write(data)

        # Copy GPX to GeoPulse path if enabled and configured
        geopulse_enable = current_app.config.get('GEOPULSE_ENABLE', False)
        geopulse_user = current_app.config.get('GEOPULSE_USER', '')
        geopulse_path = current_app.config.get('GEOPULSE_PATH', '')

        if geopulse_enable and geopulse_user and geopulse_path:
            try:
                dest_dir = os.path.join(geopulse_path, geopulse_user)
                os.makedirs(dest_dir, exist_ok=True)
                dest_file = os.path.join(dest_dir, filename)
                shutil.copy2(path, dest_file)
                current_app.logger.info(f"Copied GPX to GeoPulse: {dest_file}")
            except Exception as e:
                current_app.logger.error(f"Failed to copy GPX to GeoPulse: {e}")

        record = DownloadRecord(filename=filename)
        db.session.add(record)
        db.session.commit()
        saved += 1

    return saved



def submit_location_data_via_api(gpx_path: str) -> bool:
    """Upload a GPX file using Dawarich's API-key import endpoint (Dawarich 1.3.4+)."""
    host = (current_app.config.get('DAWARICH_HOST') or '').rstrip('/')
    api_key = current_app.config.get('DAWARICH_API_KEY')

    if not host or not api_key:
        current_app.logger.error("submit_location_data_via_api: Dawarich host or API key is not configured.")
        return False

    import_url = f'{host}/api/v1/imports'
    filename = os.path.basename(gpx_path)
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    current_app.logger.info(f"submit_location_data_via_api: Uploading {filename} to Dawarich API.")
    with open(gpx_path, 'rb') as file_handle:
        files = {'file': (filename, file_handle, content_type)}
        resp = requests.post(
            import_url,
            params={'api_key': api_key},
            files=files,
            timeout=60,
        )

    if not resp.ok:
        current_app.logger.error(
            f"submit_location_data_via_api: API import failed: {resp.status_code} - {resp.text[:500]}"
        )
        return False

    settings = UserSettings.query.first()
    if settings and settings.delete_old_gpx:
        try:
            os.remove(gpx_path)
            current_app.logger.info(f"submit_location_data_via_api: Deleted successfully uploaded file as per user setting: {gpx_path}")
        except OSError as e:
            current_app.logger.error(f"submit_location_data_via_api: Failed to delete file {gpx_path}: {e}", exc_info=True)

    current_app.logger.info(f"submit_location_data_via_api: Successfully submitted {filename} to Dawarich API.")
    return True


def submit_location_data(gpx_path: str, source: str = "gpx") -> bool:
    """Upload a GPX file to Dawarich 1.3.4 using the API-key import endpoint."""
    if not check_dawarich_connection():
        current_app.logger.error("submit_location_data: Aborting due to failed Dawarich connection check.")
        return False

    if not current_app.config.get('DAWARICH_API_KEY'):
        current_app.logger.error("submit_location_data: DAWARICH_API_KEY is required for Dawarich 1.3.4 API upload.")
        return False

    return submit_location_data_via_api(gpx_path)
