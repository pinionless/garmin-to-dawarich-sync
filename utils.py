# ========================================================
# = utils.py - Utility functions and context processors
# ========================================================
from flask import current_app
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
from models import db, DownloadRecord
import hashlib, base64

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

        path     = os.path.join(save_to, filename)
        data = gc.download_activity(
            act_id,
            dl_fmt=gc.ActivityDownloadFormat.GPX
        )
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
    current_app.logger.info(f"submit_location_data: Starting import for {gpx_path}, source={source}")
    # -- 1) LOGIN ---------------------------------------------------------
    host  = current_app.config.get('DAWARICH_HOST')
    if not host:
        current_app.logger.error("submit_location_data: DAWARICH_HOST not configured.")
        raise ValueError("DAWARICH_HOST not configured.")

    login_url =f'{host}/users/sign_in'

    user = current_app.config.get('DAWARICH_EMAIL') 
    pwd  = current_app.config.get('DAWARICH_PASSWORD')

    if not user or not pwd:
        current_app.logger.error("submit_location_data: Step 1: DAWARICH_EMAIL or DAWARICH_PASSWORD not configured.")
        raise ValueError("DAWARICH_EMAIL or DAWARICH_PASSWORD not configured.")

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