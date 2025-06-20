# ========================================================
# = index.py
# ========================================================
from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for
import datetime
from models import DownloadRecord, db
from utils import download_activities, submit_location_data
import os
import time # Added for sleep functionality

index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    pagination = DownloadRecord.query \
        .order_by(DownloadRecord.id.desc()) \
        .paginate(page=page, per_page=20)
    records = pagination.items
    return render_template('index.html', records=records, pagination=pagination)

@index_bp.route('/check')
def check():
    today     = datetime.datetime.now().date()
    yesterday = today - datetime.timedelta(days=1)
    start     = datetime.datetime.combine(yesterday, datetime.time())
    end       = datetime.datetime.now()

    try:
        count = download_activities(start, end)
        current_app.logger.info(f"/check downloaded {count} GPX files")
        flash(f"Downloaded {count} GPX file{'s' if count!=1 else ''}", "success")
    except Exception as e:
        current_app.logger.error(f"/check failed: {e}", exc_info=True)
        flash(f"Error downloading GPX files: {e}", "error")
    # go back to index page and show flash message
    return redirect(url_for('index.index'))


@index_bp.route('/upload')
def upload():
    # Retrieve GPX_FILES_DIR from config, defaulting if not set
    gpx_base_path = current_app.config.get('GPX_FILES_DIR', '/garmin/activities/')
    
    records_to_upload = DownloadRecord.query.filter(
        (DownloadRecord.dawarich == False) | (DownloadRecord.dawarich == None)
    ).order_by(DownloadRecord.id.asc()).all() # Process oldest first

    if not records_to_upload:
        flash("No new files to upload to Dawarich.", "info")
        return redirect(url_for('index.index'))

    current_app.logger.info(f"/upload: Found {len(records_to_upload)} file(s) to attempt uploading.")
    
    uploaded_count = 0
    failed_count = 0
    processed_files_details = [] # To store details for flashing

    for i, record in enumerate(records_to_upload):
        filename = record.filename
        gpx_file_path = os.path.join(gpx_base_path, filename) 

        current_app.logger.info(f"/upload: Attempting to upload {filename} (path: {gpx_file_path})")

        if not os.path.exists(gpx_file_path):
            current_app.logger.error(f"/upload: File {gpx_file_path} not found for record ID {record.id}. Skipping.")
            processed_files_details.append(f"File {filename} not found (Skipped).")
            failed_count += 1
            continue

        try:
            success = submit_location_data(gpx_file_path)
            
            if success:
                record.dawarich = True
                db.session.commit()
                current_app.logger.info(f"/upload: Successfully uploaded {filename} and updated database record ID {record.id}.")
                processed_files_details.append(f"Successfully uploaded {filename}.")
                uploaded_count += 1
            else:
                current_app.logger.warning(f"/upload: Upload of {filename} reported non-success by submit_location_data.")
                processed_files_details.append(f"Upload of {filename} reported non-success.")
                failed_count += 1
                
        except Exception as e:
            db.session.rollback() 
            current_app.logger.error(f"/upload: Failed to upload {filename}: {e}", exc_info=True)
            processed_files_details.append(f"Error uploading {filename}: {str(e)[:100]}...") # Keep error message brief for flash
            failed_count += 1
        
        # Delay before processing the next file, if it's not the last one
        if i < len(records_to_upload) - 1:
            current_app.logger.info(f"/upload: Waiting 5 seconds before next upload...")
            time.sleep(5)
            
    # Flash a summary message
    if uploaded_count > 0 and failed_count == 0:
        flash(f"Successfully uploaded {uploaded_count} file(s).", "success")
    elif uploaded_count > 0 and failed_count > 0:
        flash(f"Upload process completed. Successfully uploaded: {uploaded_count}, Failed/Skipped: {failed_count}. Check logs for details.", "warning")
    elif failed_count > 0 and uploaded_count == 0:
        flash(f"Upload process failed for all {failed_count} file(s). Check logs for details.", "error")
    # If processed_files_details is long, consider not flashing all details or logging them instead.
    # For now, we'll just flash the summary counts.

    return redirect(url_for('index.index'))




def register_routes(app):
    app.register_blueprint(index_bp)