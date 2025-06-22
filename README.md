# Garmin to Dawarich Location Sync

v0.12

This application automates the process of downloading GPX activity files from Garmin Connect and uploading them to a Dawarich instance.

## Tested Dawarich
**Works with Dawarich 0.28.1**
- Updates to Dawarich APP might break the upload(import) process.
- Check here tested, working version before upgrading Dawarich to new version.

## Support
##### Here is a link in case you want to leave a tip.
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/V7V71FGZRZ)

## Features

*   Every day at 3:00 downloads activities from Garmin Connect and imports them in Dawarich
    - Example: on 10.01.25 at 3:00 at night will download all activities from 09.01.25
*   Downloads new activities from Garmin Connect from tirgger on website
*   Stores a list of downloaded files in a PostgreSQL/LiteFS database.
*   Uploads GPX files to a Dawarich instance using its direct upload mechanism.
    - (I did not find API that could do this, so its a 'hackjob' of loading the website in python and filling the form)
*   Tracks which files have been successfully uploaded to Dawarich.
*   Web interface to view downloaded records and trigger actions.

## Prerequisites

*   Docker
*   Access to a Garmin Connect account.
*   Access to a Dawarich instance.

## Configuration

```env
environment:
    # Flask settings
    FLASK_SECRET_KEY=your_very_secret_flask_key_here
    FLASK_ENV=development # its still early beta

    # Garmin Connect Credentials
    GARMIN_EMAIL=your_garmin_email@example.com
    GARMIN_PASSWORD=your_garmin_password

    # Dawarich Instance Details
    DAWARICH_EMAIL=your_dawarich_email@example.com
    DAWARICH_PASSWORD=your_dawarich_password
    DAWARICH_HOST=https://example.com

    # Garmin activity exclusion list (optional, Python list format)
    # Example: EXCLUDE=['Virtual Ride', 'Indoor Cycling']
    EXCLUDE=[]

    # (OPTION) PostgreSQL Database(*)
    POSTGRES_USER=your_db_user
    POSTGRES_PASSWORD=your_db_password
    POSTGRES_DB=your_db_name
    POSTGRES_HOST=db

volumes: #required
    - ./garmin-to-dawarich-sync:/garmin

```
## Important
- Script does not check if location data exists in gpx file. Will upload all activities.
Exclude activities without location data using ENV EXCLUDE
- The website has no CSS file. (See To Do)
- GPX files are never deleted from mounted folder

## Database (*)
- Should set up LiteFS if POSTGRES ENV are not set (not tested yet)
- You can use same postgres container you set up for dawarich. But app requires that you create new database ("your_db_name") within that container (for example using PGAdmin).

## python-garminconnect
This project uses [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) to connect and interact with Garmin Connect services.

## Dawarich
Please support [`Dawarich`](https://github.com/Freika/dawarich)

## Usage
*   Will run at 3:00 every night.
*   Navigate to `http://localhost:5000/` to view the main page.
*   `/check`: Triggers a download of activities since yesterday until now()
*   `/upload`: Attempts to upload all unprocessed GPX files to Dawarich.

## To Do
1. CSS Styles
# Update function
2. Check if upload was sucessfull and exists in imports page
3. Check if location data exists in gpx before upload
4. Customize time and date of automatic checks
# New function:
5. Customizable manual checks

## Ready
6. Dawarich version verification - ready
7. Reupload Old Files - ready, not tested
8. Delete old gpx files - ready, tested
9. Delete old database records - ready, tested
10. Dawarich connection check - ready, not tested fully

## Example Docker Compose file
```
 garmin-to-dawarich-sync:
    container_name: garmin-to-dawarich-sync
    image: ghcr.io/pinionless/garmin-to-dawarich-sync:latest
    volumes:
      - ./garmin-to-dawarich-sync:/garmin
    environment:
      TZ: America/Denver
      FLASK_SECRET_KEY: fgxdrftg45eg5e4gerdg
      FLASK_ENV: development
      GARMIN_EMAIL: email@example.com
      GARMIN_PASSWORD: email@example.com
      EXCLUDE: "['Indoor Rowing', 'Indoor Cycling']"
      DAWARICH_EMAIL: email@example.com
      DAWARICH_PASSWORD: ABCDabcdd123
      DAWARICH_HOST: https://dawarich.example.com
      
      POSTGRES_USER: myuser
      POSTGRES_PASSWORD: mypassword
      POSTGRES_DB: garmin-to-dawarich-sync
      POSTGRES_HOST: postgres