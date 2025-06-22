# ========================================================
# = models.py - Database schema definition
# ========================================================
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# --------------------------------------------------------
# - SQLAlchemy Database Instance
#---------------------------------------------------------
# Global SQLAlchemy database instance
db = SQLAlchemy()

# --------------------------------------------------------
# - Schema Version Model
#---------------------------------------------------------
class DownloadRecord(db.Model):
    __tablename__ = 'download_records'
    id            = db.Column(db.Integer, primary_key=True)
    download_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    filename      = db.Column(db.String, nullable=False)
    dawarich      = db.Column(db.Boolean, nullable=False, default=False)


# --------------------------------------------------------
# - User Settings Model
#---------------------------------------------------------
class UserSettings(db.Model):
    __tablename__ = 'user_settings'
    id                      = db.Column(db.Integer, primary_key=True)
    delete_old_gpx          = db.Column(db.Boolean, nullable=False, default=False)
    manual_check_start_date = db.Column(db.Date, nullable=True)
    manual_check_end_date   = db.Column(db.Date, nullable=True)
    manual_check_delay   = db.Column(db.Integer, nullable=True)
    ignore_safe_dawarich_versions = db.Column(db.Boolean, nullable=False, default=False)