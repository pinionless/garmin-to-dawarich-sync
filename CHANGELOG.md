# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0]
### Added
- **User Settings**: A new "Settings" section on the UI to configure application behavior, including a manual date range check and an override for Dawarich version verification.
- **Database Models**: Added `UserSettings` table to persist user preferences.
- **File & Record Management**: Added actions to the UI to "Upload Again", "Remove File", and "Remove Record" for each download record.
- **Dawarich Connection & Version Check**: Implemented a robust connection and login check for Dawarich that also verifies the remote version against a list of safe versions.
- **Responsive Mobile UI**:
    - Added a fixed top navigation bar with icon-only buttons for mobile screens.
    - Added a fixed footer with a black background for mobile screens.
    - Added a fixed pagination bar above the footer for mobile screens.
    - Added a slide-out settings panel accessible from the mobile top navigation bar.
- **Dynamic Button Styling**:
    - "Start/Stop Custom Check" buttons now dynamically change style based on the background task's running state.
    - "Upload to Dawarich" button is now styled as primary when there are files pending upload.
    - Mobile "Settings" button turns green when the settings panel is active.
- **User Experience**:
    - Added JavaScript confirmation dialogs for all actions initiated from the mobile top navigation bar.
- **Styling**: Added a basic stylesheet (`styles.css`) for a cleaner user interface.

### Changed
- **Upload Logic**: The `/upload` route can now handle bulk uploads or single-file uploads by record ID.
- **UI Feedback**: The UI now visually indicates when a GPX file is missing from the filesystem by striking through the filename and disabling relevant actions.
- **JavaScript Refactoring**: Refactored inline JavaScript for status polling into a dedicated `static/app.js` file.
- **Mobile Layout**: Improved mobile layout for better usability on small screens, including shortened footer text and always-visible pagination controls.

### Fixed
- **Default Settings**: The application now creates a default `UserSettings` entry on first run to prevent errors.