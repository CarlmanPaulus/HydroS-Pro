# HydroS Pro Application - Migration Documentation

## Overview
This folder contains the **HydroS Pro** application - an enhanced version of the Hydrology Monitoring Suite.

**Status**: Currently has the same functionality as HydroS Standard, but uses a separate GitHub repository for independent update tracking.

## Structure
```
HydroS_Pro/
├── run_app.py                 # Main application launcher
├── requirements.txt           # Python dependencies (PySide6)
├── version.txt                # Current version (3.0.7)
├── README.md                  # Project documentation
├── HydroS.spec                # PyInstaller build specification (outputs HydroS_Pro)
├── HydroS.iss                 # Inno Setup installer script (outputs HydroS_Pro_v*_Setup)
├── .gitignore                 # Git ignore rules
│
├── manual_extractor/          # Manual GWL Extraction Tool
│   ├── main.py                # Entry point
│   ├── main_window.py         # UI components
│   ├── processing.py          # Data processing logic
│   ├── updater.py             # Update checker (GitHub: CarlmanPaulus/HydroS-Pro)
│   ├── app.qss                # Stylesheet
│   ├── HydroS.ico            # Application icon
│   ├── HydroS.png            # Logo image
│   └── __init__.py
│
├── RAW_combiner/              # RAW File Combiner Tool
│   ├── main.py                # Entry point
│   ├── main_window.py         # UI components
│   ├── processing.py          # File combination logic
│   ├── config.py              # Configuration
│   ├── app.qss                # Stylesheet
│   └── __init__.py
│
└── installer/                 # Installer resources
    └── [installer files]
```

## Configuration

### GitHub Repository
- **Repo**: `CarlmanPaulus/HydroS-Pro`
- **Release URL**: https://github.com/CarlmanPaulus/HydroS-Pro/releases
- **Update Check**: Automatic on startup, manual via "Check Updates" button

### Application Details
- **App ID**: `hydros-pro.extractor`
- **Title**: HydroS Pro
- **Version**: 3.0.7
- **Temp Directory**: `%TEMP%\HydroS Pro Temp`
- **Installer Output**: `HydroS_Pro_v3.0.7_Setup.exe`

## Running the Application

### From Python
```powershell
cd HydroS_Pro
python run_app.py
```

### After Building
```powershell
cd HydroS_Pro
pyinstaller HydroS.spec
```

## Key Features
1. **Extract GWL Tab**: Manual groundwater level data extraction
2. **Combine RAW Tab**: Combine multiple RAW sensor files
3. **Theme Toggle**: Light/Dark mode switching
4. **Auto-Updates**: Checks for patches and major versions on independent GitHub repo

## Update System
- **Minor Updates**: Patch `.zip` files (auto-applied)
- **Major Updates**: Full installer (`.exe`/`.msi`)
- **Repo**: CarlmanPaulus/HydroS-Pro (independent from standard version)

## Differences from Standard HydroS
| Aspect | HydroS | HydroS Pro |
|--------|--------|-----------|
| GitHub Repo | CarlmanPaulus/HydroS | CarlmanPaulus/HydroS-Pro |
| App ID | hydros.extractor | hydros-pro.extractor |
| Window Title | HydroS | HydroS Pro |
| Executable Name | HydroS.exe | HydroS_Pro.exe |
| Temp Folder | HydroS Temp | HydroS Pro Temp |
| Update System | Independent | Independent |
| Can Install Together | Yes | Yes |

## Coexistence
Both HydroS and HydroS Pro can be installed on the same system simultaneously:
- Different executable names prevent conflicts
- Different GitHub repos for independent update tracking
- Different temp directories for update storage
- Can run both at the same time

## Related Folder
See `../HydroS/` for the standard version with the same current functionality.
