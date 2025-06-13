# ========================================================
# = index.py
# ========================================================
from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for
import datetime
from models import DownloadRecord, db
from utils import download_activities, submit_location_data
import os

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
    end       = datetime.datetime.combine(yesterday, datetime.time.max)

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
    record_to_upload = DownloadRecord.query.filter(
        (DownloadRecord.dawarich == False) | (DownloadRecord.dawarich == None)
    ).order_by(DownloadRecord.id.desc()).first()

    if not record_to_upload:
        flash("No new files to upload to Dawarich.", "info")
        return redirect(url_for('index.index'))

    filename = record_to_upload.filename
    gpx_file_path = os.path.join("/garmin/activities/", filename) 

    current_app.logger.info(f"/upload: Attempting to upload {filename} (path: {gpx_file_path})")

    if not os.path.exists(gpx_file_path):
        current_app.logger.error(f"/upload: File {gpx_file_path} not found for record ID {record_to_upload.id}.")
        flash(f"File {filename} not found. Skipping upload.", "error")
        return redirect(url_for('index.index'))

    try:
        success = submit_location_data(gpx_file_path)
        
        if success:
            record_to_upload.dawarich = True
            db.session.commit()
            current_app.logger.info(f"/upload: Successfully uploaded {filename} and updated database record ID {record_to_upload.id}.")
            flash(f"Successfully uploaded {filename} to Dawarich.", "success")
        else:
            current_app.logger.warning(f"/upload: Upload of {filename} reported non-success by submit_location_data.")
            flash(f"Upload of {filename} to Dawarich completed but reported non-success.", "warning")
            
    except Exception as e:
        db.session.rollback() 
        current_app.logger.error(f"/upload: Failed to upload {filename}: {e}", exc_info=True)
        flash(f"Error uploading {filename} to Dawarich: {e}", "error")
        
    return redirect(url_for('index.index'))




def register_routes(app):
    app.register_blueprint(index_bp)