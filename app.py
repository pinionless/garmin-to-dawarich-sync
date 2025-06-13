# ========================================================
# = app.py
# ========================================================
import os
import ast
from flask import Flask, jsonify
from models import db
from werkzeug.exceptions import BadRequest
import index

# --------------------------------------------------------
# - Application Version
#---------------------------------------------------------
__version__ = "0.10" # Current application version
APP_TITLE = "Garmin to Dawarich Location Sync"
TARGET_DB_SCHEMA_VERSION = "0.10"

# --------------------------------------------------------
# - Application Factory Function
#---------------------------------------------------------
def create_app():
    # == Flask App Initialization ============================================
    app = Flask(__name__)

    # == Configuration Settings ============================================
    # -- General Flask Configuration -------------------
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_keyADFGHSAVZX')
    app.config['TARGET_DB_SCHEMA_VERSION'] = TARGET_DB_SCHEMA_VERSION
    app.config['GARMIN_EMAIL'] = os.environ.get('GARMIN_EMAIL')
    app.config['GARMIN_PASSWORD'] = os.environ.get('GARMIN_PASSWORD')
    app.config['DAWARICH_EMAIL'] = os.environ.get('DAWARICH_EMAIL')
    app.config['DAWARICH_PASSWORD'] = os.environ.get('DAWARICH_PASSWORD')
    app.config['DAWARICH_HOST'] = os.environ.get('DAWARICH_HOST')

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

    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}' # SQLAlchemy database URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable SQLAlchemy event system
    
    # == Database Initialization ============================================
    db.init_app(app)  # Initialize SQLAlchemy with the Flask app

    # == Ensure all tables exist and perform schema checks inside context ==
    with app.app_context():
        db.create_all()

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