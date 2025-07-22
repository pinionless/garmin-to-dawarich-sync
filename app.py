# ========================================================
# = app.py
# ========================================================
import os
import ast
from flask import Flask, jsonify, request
from models import db, UserSettings
from werkzeug.exceptions import BadRequest
import index
import datetime # Added for date calculations
from apscheduler.schedulers.background import BackgroundScheduler # Added for scheduling
from utils import download_activities, scheduled_download_job, check_dawarich_connection

# --------------------------------------------------------
# - Application Version
#---------------------------------------------------------
__version__ = "0.14" # Current application version
APP_TITLE = "Garmin to Dawarich Location Sync"

# --------------------------------------------------------
# - Application Factory Function
#---------------------------------------------------------
def create_app():
    # == Flask App Initialization ============================================
    app = Flask(__name__)

    # == Configuration Settings ============================================
    # -- General Flask Configuration -------------------
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_keyADFGHSAVZX')
    app.config['GARMIN_EMAIL'] = os.environ.get('GARMIN_EMAIL')
    app.config['GARMIN_PASSWORD'] = os.environ.get('GARMIN_PASSWORD')
    app.config['DAWARICH_EMAIL'] = os.environ.get('DAWARICH_EMAIL')
    app.config['DAWARICH_PASSWORD'] = os.environ.get('DAWARICH_PASSWORD')
    app.config['DAWARICH_HOST'] = os.environ.get('DAWARICH_HOST')
    app.config['_DAWARICH_CONNECTION_STATUS'] = {'status': None, 'timestamp': None, 'message': '', 'version': None}
    app.config['CUSTOM_CHECK_TASK'] = {'thread': None, 'stop_event': None, 'status_message': 'Not running.'}
    app.config['SAFE_VERSIONS'] = ['0.28.1', '0.29.1', '0.30.0']

    raw = os.environ.get('EXCLUDE', '[]')
    try:
        app.config['EXCLUDE'] = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        app.config['EXCLUDE'] = []
    
    # -- Database Configuration -------------------
    DB_USER = os.environ.get('POSTGRES_USER') # PostgreSQL username
    DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD') # PostgreSQL password
    DB_NAME = os.environ.get('POSTGRES_DB') # PostgreSQL database name
    DB_HOST = os.environ.get('POSTGRES_HOST', 'db') # PostgreSQL host

    # Check if PostgreSQL environment variables are set
    if DB_USER and DB_PASSWORD and DB_NAME:
        # Use PostgreSQL
        app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}'
        app.logger.info("Using PostgreSQL database.")
    else:

        litefs_db_path = os.environ.get('LITEFS_DB_PATH', '/garmin/litefs.db')
        # Ensure the directory for the SQLite database exists
        os.makedirs(os.path.dirname(litefs_db_path), exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{litefs_db_path}'
        app.logger.info(f"PostgreSQL environment variables not fully set. Using LiteFS (SQLite) at {litefs_db_path}.")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable SQLAlchemy event system
    
    # == Database Initialization ============================================
    db.init_app(app)  # Initialize SQLAlchemy with the Flask app

    # == Initialize Scheduler ===============================================
    # Note: In a production environment with multiple workers (e.g., Gunicorn),
    # ensure the scheduler is initialized and run by only one worker/process
    # to avoid duplicate job executions.
    # For Flask's dev server with reloader, this check helps prevent duplicates.
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler(daemon=True)
        # Schedule the job to run daily at 3:00 AM
        scheduler.add_job(
            func=scheduled_download_job, # Now uses the imported function
            args=[app], # Pass the app instance to the job
            trigger='cron',
            hour=3,
            minute=0
        )
        scheduler.start()
        app.logger.info("Scheduler started. Daily download job scheduled for 3:00 AM.")

    # == Ensure all tables exist and perform schema checks inside context ==
    with app.app_context():
        db.create_all()

        # Check if UserSettings has any entries. If not, create a default one.
        if UserSettings.query.count() == 0:
            default_settings = UserSettings()
            db.session.add(default_settings)
            db.session.commit()
            app.logger.info("Created default user settings.")

    @app.before_request
    def before_request_func():
        # Don't run the check for static files to avoid unnecessary checks
        if request.endpoint and 'static' not in request.endpoint:
            check_dawarich_connection()

    # == Inject App Version into Templates ============================================
    @app.context_processor
    def inject_version():
        # Makes app_version available in all templates
        return dict(app_version=__version__)

    # == Register Blueprints for different application modules ============================================
    # Each blueprint corresponds to a feature or section of the application
    # Registers routes for index page
    index.register_routes(app)

    # Suppress raw‐bytes logs for protocol‐mismatch 400s (e.g. HTTPS→HTTP)
    @app.errorhandler(BadRequest)
    def handle_bad_request(e):
        app.logger.warning(f"Bad request received: {e.description}")
        return jsonify(status="error", message="Bad request"), 400
    return app

# --------------------------------------------------------
# - Main Execution Block
#---------------------------------------------------------
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)