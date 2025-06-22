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
