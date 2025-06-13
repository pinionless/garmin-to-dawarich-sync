# Garmin to Dawarich Location Sync

Version: 0.10

This application automates the process of downloading GPX activity files from Garmin Connect and uploading them to a Dawarich instance.

## Features

*   Downloads new activities from Garmin Connect.
*   Stores a record of downloaded files in a PostgreSQL database.
*   Uploads GPX files to a Dawarich instance using its direct upload mechanism.
*   Tracks which files have been successfully uploaded to Dawarich.
*   Web interface to view downloaded records and trigger actions.

## Prerequisites

*   Docker and Docker Compose (for running with PostgreSQL)
*   Access to a Garmin Connect account.
*   Access to a Dawarich instance.

## Configuration

The application is configured using environment variables. Create a `.env` file in the project root or set these variables in your deployment environment:

```env
# Flask settings
FLASK_SECRET_KEY=your_very_secret_flask_key_here
FLASK_ENV=development # or production

# Garmin Connect Credentials
GARMIN_EMAIL=your_garmin_email@example.com
GARMIN_PASSWORD=your_garmin_password

# PostgreSQL Database (if using Docker, these often match docker-compose.yml)
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_DB=your_db_name
POSTGRES_HOST=db # or localhost if running PostgreSQL directly

# Dawarich Instance Details
DAWARICH_EMAIL=your_dawarich_email@example.com
DAWARICH_PASSWORD=your_dawarich_password
DAWARICH_HOST=https://example.com

# Garmin activity exclusion list (optional, Python list format)
# Example: EXCLUDE=['Virtual Ride', 'Indoor Cycling']
EXCLUDE=[]

# volumes:
    - ./garmin-to-dawarich-sync:/garmin

```




## Usage
*   Navigate to `http://localhost:5000/` to view the main page.
*   `/check`: Triggers a download of yesterday's activities from Garmin Connect.
*   `/upload`: Attempts to upload the oldest unprocessed GPX file to Dawarich.
*   `/test`: Triggers a test of the ActiveStorage direct upload mechanism against Dawarich (for debugging).