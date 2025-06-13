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