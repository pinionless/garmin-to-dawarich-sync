# Changelog

All notable changes to this project will be documented in this file.


## [0.12]

### Added
- **User Settings**: A new "Settings" section on the UI to configure application behavior.
- **Database Models**: Added `UserSettings` table to persist user preferences.
- **Manual Date Range Check**: Users can now specify a start and end date in settings for a manual activity check.
- **File & Record Management**: Added actions to the UI to "Upload Again", "Remove File", and "Remove Record" for each download record.
- **Dawarich Connection Check**: Implemented a robust connection and login check for Dawarich that runs on application start and before uploads.
- **Dawarich Version Verification**: The application now checks the Dawarich version against a list of safe, tested versions to prevent issues from breaking changes. An override setting (`ignore_safe_dawarich_versions`) has been added.
- **Styling**: Added a basic stylesheet (`styles.css`) for a cleaner and more compact user interface.

### Changed
- **Upload Logic**: The `/upload` route can now handle bulk uploads or single-file uploads by record ID.
- **UI Feedback**: The UI now visually indicates when a GPX file is missing from the filesystem by striking through the filename and disabling relevant actions.

### Fixed
- **Default Settings**: The application now creates a default `UserSettings` entry on first run to prevent errors.

### Added
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
    - Background task status is now polled via an external `app.js` file instead of inline script.

### Changed
- Refactored inline JavaScript for status polling into `static/app.js`.
- Improved mobile layout for better usability on small screens.
- Footer text is shortened on mobile view for a minimal look.
- Pagination controls are now always visible on mobile.