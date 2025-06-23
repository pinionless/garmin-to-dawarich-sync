# Garmin to Dawarich Location Sync

This application automates the process of downloading GPX activity files from Garmin Connect and uploading them to a Dawarich instance.

## Tested Dawarich
**Works with Dawarich 0.28.1**
- Updates to the Dawarich app might break the upload (import) process.
- By default, the application will only work with tested versions of Dawarich. This can be changed in settings.

## Support
##### Here is a link in case you want to leave a tip.
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/V7V71FGZRZ)

## Features
*   **Automated Sync**: Runs a scheduled job daily (at 3:00 AM) to download yesterday's activities from Garmin Connect and upload them to Dawarich.
*   **Manual Controls**: Trigger downloads and uploads manually through the web interface.
*   **Historical Download**: A "Custom Check" feature allows downloading historical data for a specified date range, with a configurable delay to avoid rate-limiting.
*   **Responsive Web UI**: A clean web interface that works on both desktop and mobile devices for viewing records and managing the application.
*   **Intelligent Downloading**: Skips activities that have already been downloaded or do not contain any GPS location data.
*   **Robust Uploading**: Simulates browser behavior to robustly upload GPX files to Dawarich's direct upload endpoint.
*   **Connection & Version Checks**: Performs pre-flight checks for Dawarich connection, credentials, and version compatibility to prevent errors.
*   **Persistent Database**: Uses PostgreSQL or LiteFS (SQLite) to store a record of all downloaded files and their upload status.

## Historical Download
    - You can download historical location data from any period of time from garmin.
    - Set start and end dates in settings and run "Custom Check"
    - The script will download one day at a time and with a delay proceed to next one.
    - For significant time period please consider settings larger delay to avoid getting flagged/banned by Garmin Connect.
    - After GPX files are downloaded you have to trigger manual upload to Dawarich

## Prerequisites

*   Docker
*   A Garmin Connect account.
*   A Dawarich instance.

## Configuration

Configuration is managed via environment variables. Below is an example snippet for a `docker-compose.yml` file.

```yaml
environment:
    # Flask settings
    FLASK_SECRET_KEY: "your_very_secret_flask_key_here"
    FLASK_ENV: "development"

    # Garmin Connect Credentials
    GARMIN_EMAIL: "your_garmin_email@example.com"
    GARMIN_PASSWORD: "your_garmin_password"

    # Dawarich Instance Details
    DAWARICH_EMAIL: "your_dawarich_email@example.com"
    DAWARICH_PASSWORD: "your_dawarich_password"
    DAWARICH_HOST: "https://dawarich.example.com"

    # Garmin activity exclusion list (optional, Python list format)
    # Example: EXCLUDE: "['Virtual Ride', 'Indoor Cycling']"
    EXCLUDE: "[]"

    # (Optional) PostgreSQL Database Details
    POSTGRES_USER: "your_db_user"
    POSTGRES_PASSWORD: "your_db_password"
    POSTGRES_DB: "your_db_name"
    POSTGRES_HOST: "db" # Often the service name in docker-compose
```

## Database
- The application will automatically use a local **LiteFS (SQLite)** database located in the `/garmin` volume if PostgreSQL environment variables are not fully provided.
- To use **PostgreSQL**, you can use the same container as your Dawarich instance, but you must create a new, separate database for this application (e.g., using PGAdmin).

## python-garminconnect
This project uses [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) to connect and interact with Garmin Connect services.

## Dawarich
Please support [`Dawarich`](https://github.com/Freika/dawarich).

## Usage
*   The automated job runs at 3:00 AM every night according to the container's timezone.
*   Navigate to `http://localhost:5000/` (or your mapped port) to access the web interface.

## To Do
1. Verify that an upload was successful by checking the Dawarich imports page.
2. Allow customization of the scheduled job's time.
3. Better styles for PC.
4. Delete files if upload to Dawarich was successful.

## Example Docker Compose file
```yaml
services:
  garmin-to-dawarich-sync:
    container_name: garmin-to-dawarich-sync
    image: ghcr.io/pinionless/garmin-to-dawarich-sync:latest
    volumes:
      - ./garmin-to-dawarich-sync:/garmin
    environment:
      TZ: "America/Denver"
      FLASK_SECRET_KEY: "fgxdrftg45eg5e4gerdg"
      FLASK_ENV: "development"
      GARMIN_EMAIL: "email@example.com"
      GARMIN_PASSWORD: "email@example.com"
      EXCLUDE: "['Indoor Rowing', 'Indoor Cycling']"
      DAWARICH_EMAIL: "email@example.com"
      DAWARICH_PASSWORD: "ABCDabcdd123"
      DAWARICH_HOST: "https://dawarich.example.com"
      
      # Optional PostgreSQL connection
      POSTGRES_USER: "myuser"
      POSTGRES_PASSWORD: "mypassword"
      POSTGRES_DB: "garmin-to-dawarich-sync"
      POSTGRES_HOST: "postgres" # Assumes a service named 'postgres'
```