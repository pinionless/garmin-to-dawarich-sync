# ========================================================
# = index.py
# ========================================================
from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
import datetime
from models import DownloadRecord, db, UserSettings
from utils import download_activities, submit_location_data, run_custom_check
import os
import time # Added for sleep functionality
import threading

index_bp = Blueprint('index', __name__)

@index_bp.route('/custom_check_status')
def custom_check_status():
    task_info = current_app.config['CUSTOM_CHECK_TASK']
    is_running = task_info.get('thread') and task_info['thread'].is_alive()
    message = task_info.get('status_message', 'N/A')
    return jsonify(is_running=is_running, message=message)

@index_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    pagination = DownloadRecord.query \
        .order_by(DownloadRecord.id.desc()) \
        .paginate(page=page, per_page=20)
    records = pagination.items
    settings = UserSettings.query.first()

    task_info = current_app.config['CUSTOM_CHECK_TASK']
    is_custom_check_running = task_info.get('thread') and task_info['thread'].is_alive()

    has_pending_uploads = db.session.query(DownloadRecord.query.filter(
        (DownloadRecord.dawarich == False) | (DownloadRecord.dawarich == None)
    ).exists()).scalar()

    gpx_base_path = current_app.config.get('GPX_FILES_DIR', '/garmin/activities/')
    for rec in records:
        gpx_file_path = os.path.join(gpx_base_path, rec.filename)
        rec.file_exists = os.path.exists(gpx_file_path)

    return render_template('index.html', records=records, pagination=pagination, settings=settings, is_custom_check_running=is_custom_check_running, has_pending_uploads=has_pending_uploads)

@index_bp.route('/settings', methods=['POST'])
def settings():
    settings = UserSettings.query.first()
    if not settings:
        flash("Settings could not be found to update.", "error")
        return redirect(url_for('index.index'))

    settings.delete_old_gpx = 'delete_old_gpx' in request.form
    settings.ignore_safe_dawarich_versions = 'ignore_safe_dawarich_versions' in request.form

    start_date_str = request.form.get('manual_check_start_date')
    if start_date_str:
        settings.manual_check_start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        settings.manual_check_start_date = None

    end_date_str = request.form.get('manual_check_end_date')
    if end_date_str:
        settings.manual_check_end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        settings.manual_check_end_date = None

    delay_val = request.form.get('manual_check_delay_seconds')
    if delay_val and delay_val.isdigit():
        settings.manual_check_delay_seconds = int(delay_val)
    else:
        settings.manual_check_delay_seconds = None
    
    db.session.commit()
    flash("Settings updated successfully.", "success")
    return redirect(url_for('index.index'))


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


@index_bp.route('/start_custom_check')
def start_custom_check():
    task_info = current_app.config['CUSTOM_CHECK_TASK']
    if task_info.get('thread') and task_info['thread'].is_alive():
        flash("A custom check is already running.", "warning")
        return redirect(url_for('index.index'))

    settings = UserSettings.query.first()
    if not all([settings.manual_check_start_date, settings.manual_check_end_date, settings.manual_check_delay_seconds is not None]):
        flash("Please set a valid start date, end date, and delay for the custom check in Settings.", "error")
        return redirect(url_for('index.index'))

    if settings.manual_check_start_date > settings.manual_check_end_date:
        flash("Start date cannot be after the end date.", "error")
        return redirect(url_for('index.index'))

    stop_event = threading.Event()
    # Pass the real app object to the thread, not the proxy
    thread = threading.Thread(target=run_custom_check, args=(current_app._get_current_object(), stop_event))
    
    task_info['thread'] = thread
    task_info['stop_event'] = stop_event
    
    thread.start()
    
    flash("Custom check has been started in the background.", "info")
    return redirect(url_for('index.index'))


@index_bp.route('/stop_custom_check')
def stop_custom_check():
    task_info = current_app.config['CUSTOM_CHECK_TASK']
    if task_info.get('thread') and task_info['thread'].is_alive():
        if task_info.get('stop_event'):
            task_info['stop_event'].set()
            flash("Sent stop signal to custom check task. It will stop after the current day's processing.", "info")
        else:
            flash("Cannot stop the task: no stop event found.", "error")
    else:
        flash("No custom check task is currently running.", "warning")
        # Clean up just in case
        task_info['thread'] = None
        task_info['stop_event'] = None

    return redirect(url_for('index.index'))


@index_bp.route('/upload')
@index_bp.route('/upload/<int:record_id>')
def upload(record_id=None):
    # Retrieve GPX_FILES_DIR from config, defaulting if not set
    gpx_base_path = current_app.config.get('GPX_FILES_DIR', '/garmin/activities/')
    
    if record_id:
        records_to_upload = DownloadRecord.query.filter_by(id=record_id).all()
    else:
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
            current_app.logger.info(f"/upload: Waiting 2 seconds before next upload...")
            time.sleep(2)
            
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


@index_bp.route('/remove_file/<int:record_id>')
def remove_file(record_id):
    record = DownloadRecord.query.get_or_404(record_id)
    gpx_base_path = current_app.config.get('GPX_FILES_DIR', '/garmin/activities/')
    gpx_file_path = os.path.join(gpx_base_path, record.filename)

    if os.path.exists(gpx_file_path):
        try:
            os.remove(gpx_file_path)
            flash(f"Successfully removed file: {record.filename}", "success")
            current_app.logger.info(f"Removed file {gpx_file_path} for record ID {record.id}")
        except OSError as e:
            flash(f"Error removing file {record.filename}: {e}", "error")
            current_app.logger.error(f"Error removing file {gpx_file_path}: {e}", exc_info=True)
    else:
        flash(f"File not found, could not remove: {record.filename}", "warning")
        current_app.logger.warning(f"File {gpx_file_path} not found for removal for record ID {record.id}")

    return redirect(url_for('index.index'))


@index_bp.route('/remove_record/<int:record_id>')
def remove_record(record_id):
    record = DownloadRecord.query.get_or_404(record_id)
    try:
        db.session.delete(record)
        db.session.commit()
        flash(f"Successfully removed record ID: {record.id}", "success")
        current_app.logger.info(f"Removed record ID {record.id} from database.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing record ID {record.id}: {e}", "error")
        current_app.logger.error(f"Error removing record ID {record.id}: {e}", exc_info=True)

    return redirect(url_for('index.index'))


def register_routes(app):
    app.register_blueprint(index_bp)