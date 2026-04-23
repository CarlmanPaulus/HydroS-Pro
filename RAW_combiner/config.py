"""Site and directory configuration for RAW Files Combiner."""

import json as _json
import os
import string

# ═══════════════════════════════════════════════════════════════════════════
# Preferences (JSON config stored in %APPDATA%\HydroS\config_HydroS.json)
# ═══════════════════════════════════════════════════════════════════════════
_appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
_CONFIG_DIR = os.path.join(_appdata, "HydroS")
os.makedirs(_CONFIG_DIR, exist_ok=True)
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config_HydroS.json")
_CONFIG_SECTION = "combiner"


def _load_all():
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r") as f:
                return _json.load(f)
        except (_json.JSONDecodeError, OSError):
            pass
    return {}


def _save_all(data):
    with open(_CONFIG_FILE, "w") as f:
        _json.dump(data, f, indent=2)


def load_config():
    return _load_all().get(_CONFIG_SECTION, {})


def save_config(cfg):
    data = _load_all()
    data[_CONFIG_SECTION] = cfg
    _save_all(data)


# ═══════════════════════════════════════════════════════════════════════════
# Google Drive auto-detection
# ═══════════════════════════════════════════════════════════════════════════
_MY_DRIVE = "My Drive"
_WT_REL = os.path.join("Hydrology Research", "WT", "MARUDI_WT")


def detect_google_drive_roots():
    roots = []
    home = os.path.expanduser("~")
    for sub in [
        _MY_DRIVE,
        os.path.join("Google Drive", _MY_DRIVE),
        os.path.join("Google Drive Stream", _MY_DRIVE),
        os.path.join("GoogleDrive", _MY_DRIVE),
    ]:
        candidate = os.path.join(home, sub)
        if os.path.isdir(candidate):
            roots.append(candidate)
    for letter in string.ascii_uppercase:
        candidate = f"{letter}:\\{_MY_DRIVE}"
        if os.path.isdir(candidate) and candidate not in roots:
            roots.append(candidate)
    return roots


def _find_wt_base():
    """Find the MARUDI_WT base path from available Google Drive roots."""
    for root in detect_google_drive_roots():
        candidate = os.path.join(root, _WT_REL)
        if os.path.isdir(candidate):
            return candidate
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Site definitions
# ═══════════════════════════════════════════════════════════════════════════
SITE_GROUPS = {
    "Tasong": {
        "color": "#D5E8D4",
        "subdirs": ["SSD8_baro", "SSD8_wt1", "SSD8_wt2"],
    },
    "Marau": {
        "color": "#D4E4FF",
        "subdirs": [
            "SSD1_baro", "SSD1_wt1", "SSD1_wt2",
            "SSD2_baro", "SSD2_wt1", "SSD2_wt2",
            "SSD3_baro", "SSD3_wt1", "SSD3_wt2",
        ],
    },
    "Marudi": {
        "color": "#FF7F7F",
        "subdirs": [
            "SSD10_baro", "SSD10_wt1", "SSD10_wt2",
            "SSD11_baro", "SSD11_wt1", "SSD11_wt2",
            "SSD12_baro", "SSD12_wt1", "SSD12_wt2",
            "SSD13_baro", "SSD13_wt1", "SSD13_wt2",
            "SSD14_baro", "SSD14_wt1", "SSD14_wt2",
            "SSD15_baro", "SSD15_wt1", "SSD15_wt2",
        ],
    },
}


def get_default_site_base(site_name):
    """Return the auto-detected default base path for a site, or empty string."""
    wt_base = _find_wt_base()
    if wt_base:
        candidate = os.path.join(wt_base, site_name)
        if os.path.isdir(candidate):
            return candidate
    return ""


def get_initial_site_paths():
    """Load saved site paths from config, falling back to auto-detected defaults."""
    cfg = load_config()
    saved = cfg.get("site_paths", {})
    paths = {}
    for site_name in SITE_GROUPS:
        saved_path = saved.get(site_name, "")
        if saved_path and os.path.isdir(saved_path):
            paths[site_name] = saved_path
        else:
            paths[site_name] = get_default_site_base(site_name)
    return paths


def save_site_paths(site_paths):
    """Persist the user's chosen site base paths."""
    cfg = load_config()
    cfg["site_paths"] = dict(site_paths)
    save_config(cfg)


def build_directories(site_paths=None):
    """Build list of (label, full_path) tuples for all site subdirectories.

    Parameters
    ----------
    site_paths : dict, optional
        {site_name: base_dir_path}. If None, uses auto-detected defaults.
    """
    if site_paths is None:
        site_paths = get_initial_site_paths()

    result = {}
    for site_name, info in SITE_GROUPS.items():
        site_base = site_paths.get(site_name, "")
        entries = []
        for subdir in info["subdirs"]:
            full = os.path.join(site_base, subdir) if site_base else ""
            entries.append((subdir, full))
        result[site_name] = entries
    return result
