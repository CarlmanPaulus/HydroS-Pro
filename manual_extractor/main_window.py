import os
import sys
import string
import subprocess
import tempfile
import pandas as pd
from datetime import datetime, date
from threading import Thread
import webbrowser
from PySide6.QtCore import QEvent

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QCheckBox, QProgressBar,
    QTextEdit, QFileDialog, QDateEdit, QFrame,
    QGridLayout, QSizePolicy, QDialog, QTableView, QCalendarWidget, QToolButton,
)
from PySide6.QtCore import QDate, Signal, QObject, Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QIcon, QTextCharFormat, QTextCursor, QPainter, QPen, QConicalGradient

from .processing import format_duration, process_pipe
from .updater import (
    RELEASE_URL,
    check_for_updates as updater_check_for_updates,
    cleanup_update_downloads,
    download_file,
    extract_patch_zip,
    fetch_latest_release,
    get_install_dir,
    get_update_download_dir,
    is_major_update,
    make_unique_path,
    select_installer_asset,
    select_zip_asset,
    write_patch_script,
)

APP_ID = "hydros.extractor"
WINDOW_TITLE = "HydroS — Manual Extractor"
CALENDAR_POPUP_WIDTH = 330
UI_FONT_TITLE = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Arial"'
UI_FONT_BODY = '"Segoe UI Variable Text", "Segoe UI", "Arial"'
UI_FONT_MONO = '"Cascadia Mono", "JetBrains Mono", "Consolas", "Courier New"'

CURRENT_VERSION = "3.0.7"
VALID_THEMES = ("dark", "light")
DEFAULT_THEME = "dark"

THEME_COLORS = {
    "dark": {
        "file_name": "#18d0ff",
        "outdir": "#8fdcff",
        "status_text": "#d4dce6",
        "current_item": "#ff9bd5",
        "section_accent": "#00b4d8",
        "selected_idle": ("#ddf8ff", "#153548", "#266f8d"),
        "selected_active": ("#e9fff4", "#154533", "#2da56b"),
        "status_ready": ("#dff7ff", "#184058", "#2c7ea1"),
        "dialog_bg": "#162230",
        "dialog_border": "#253545",
        "dialog_title": "#ffffff",
        "dialog_text": "#d4dce6",
        "dialog_hover_bg": "#ffffff",
        "dialog_hover_text": "#162230",
        "dialog_pressed_bg": "#0a1520",
        "dialog_pressed_text": "#ffffff",
        "start_disabled_bg": "#243746",
        "start_disabled_border": "#31475a",
        "start_disabled_text": "#6f8598",
        "abort_disabled_bg": "#332426",
        "abort_disabled_border": "#4d3135",
        "abort_disabled_text": "#967f82",
        "theme_toggle_active": ("#ffffff", "#00b4d8", "#45dcf8"),
        "theme_toggle_inactive": ("#cde8f5", "#24465f", "#3f6e90"),
        "log_colors": {
            "info": "#00b4d8",
            "ok": "#00e676",
            "warn": "#ffb347",
            "err": "#ff5252",
            "white": "#d4dce6",
        },
    },
    "light": {
        "file_name": "#0a6f9d",
        "outdir": "#234e67",
        "status_text": "#18384c",
        "current_item": "#962d73",
        "section_accent": "#00a4cc",
        "selected_idle": ("#153f58", "#deeff8", "#74a8c4"),
        "selected_active": ("#14553f", "#e0f6eb", "#68b592"),
        "status_ready": ("#153f58", "#dfeff8", "#78aac6"),
        "dialog_bg": "#f7fbff",
        "dialog_border": "#b9cedd",
        "dialog_title": "#173246",
        "dialog_text": "#1d3b4f",
        "dialog_hover_bg": "#dbeef8",
        "dialog_hover_text": "#173246",
        "dialog_pressed_bg": "#bcd7e7",
        "dialog_pressed_text": "#173246",
        "start_disabled_bg": "#d6e2ea",
        "start_disabled_border": "#bccbd7",
        "start_disabled_text": "#5f7382",
        "abort_disabled_bg": "#ead7da",
        "abort_disabled_border": "#d7bcc0",
        "abort_disabled_text": "#88686e",
        "theme_toggle_active": ("#173246", "#d2ecf7", "#84b9d1"),
        "theme_toggle_inactive": ("#2f4c60", "#edf4f9", "#a8c0cf"),
        "log_colors": {
            "info": "#086e9d",
            "ok": "#0b7648",
            "warn": "#8e5809",
            "err": "#ad3030",
            "white": "#183548",
        },
    },
}

def resource_path(filename):
    """Return correct path whether running as script or PyInstaller exe."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def normalize_theme_name(theme_name):
    theme_name = (theme_name or DEFAULT_THEME).strip().lower()
    return theme_name if theme_name in VALID_THEMES else DEFAULT_THEME


# ═══════════════════════════════════════════════════════════════════════════
# Site / pipe configuration
# ═══════════════════════════════════════════════════════════════════════════
PIPE_GROUPS = [
    ("Marau",  ["SSD1_1", "SSD1_2", "SSD2_1", "SSD2_2", "SSD3_1", "SSD3_2"]),
    ("Tasong", ["SSD8_1", "SSD8_2"]),
    ("Marudi", ["SSD10_1", "SSD10_2", "SSD11_1", "SSD11_2", "SSD12_1", "SSD12_2",
                "SSD13_1", "SSD13_2", "SSD14_1", "SSD14_2", "SSD15_1", "SSD15_2"]),
]

# Flat list for processing (keyed under sheet name "WT_Marudi")
SITES_AND_PIPES = {
    "WT_Marudi": [pipe for _, pipes in PIPE_GROUPS for pipe in pipes],
}

# ═══════════════════════════════════════════════════════════════════════════
# Google Drive auto-detection & portable path helpers
# ═══════════════════════════════════════════════════════════════════════════
_GDRIVE_REL_DIR = os.path.join("Hydrology Research", "Manual WT Google Sheet", "Split MWT")
_GDRIVE_DEFAULT_FILE = "2025-08-19-P14_WT_Manual.xlsx"
_MY_DRIVE = "My Drive"


def detect_google_drive_roots():
    roots = []
    home = os.path.expanduser("~")
    for sub in [_MY_DRIVE,
                os.path.join("Google Drive", _MY_DRIVE),
                os.path.join("Google Drive Stream", _MY_DRIVE),
                os.path.join("GoogleDrive", _MY_DRIVE)]:
        candidate = os.path.join(home, sub)
        if os.path.isdir(candidate):
            roots.append(candidate)
    for letter in string.ascii_uppercase:
        candidate = f"{letter}:\\{_MY_DRIVE}"
        if os.path.isdir(candidate) and candidate not in roots:
            roots.append(candidate)
    return roots


def resolve_gdrive_path(rel_path, hint_root=None):
    roots = detect_google_drive_roots()
    if hint_root and hint_root in roots:
        roots.remove(hint_root)
        roots.insert(0, hint_root)
    for root in roots:
        full = os.path.join(root, rel_path)
        if os.path.exists(full):
            return full
    return None


def to_gdrive_relative(abs_path):
    abs_norm = os.path.normpath(abs_path)
    for root in detect_google_drive_roots():
        root_norm = os.path.normpath(root)
        if abs_norm.lower().startswith(root_norm.lower() + os.sep) or abs_norm.lower() == root_norm.lower():
            rel = os.path.relpath(abs_norm, root_norm)
            return rel, root_norm
    return None, None


# ═══════════════════════════════════════════════════════════════════════════
# Preferences (JSON config stored in %APPDATA%\HydroS\config_HydroS.json)
# ═══════════════════════════════════════════════════════════════════════════
import json as _json

_appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
_CONFIG_DIR = os.path.join(_appdata, "HydroS")
os.makedirs(_CONFIG_DIR, exist_ok=True)
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config_HydroS.json")
_CONFIG_SECTION = "extractor"


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


def _load_section(section):
    return _load_all().get(section, {})


def _save_section(section, cfg):
    data = _load_all()
    data[section] = cfg
    _save_all(data)
COMBINER_CANDIDATES = [
    "1.2.2 RAW Files Combiner.py",
    "1.2.1 RAW Files Combiner.py",
    "1.2.1 WT Combine multiple raw file WLL.py",
]


def load_config():
    return _load_section(_CONFIG_SECTION)


def save_config(cfg):
    _save_section(_CONFIG_SECTION, cfg)


def project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def find_combiner_script():
    root = project_root()
    for candidate in COMBINER_CANDIDATES:
        full_path = os.path.join(root, candidate)
        if os.path.exists(full_path):
            return full_path
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Resolve initial paths
# ═══════════════════════════════════════════════════════════════════════════
_cfg = load_config()
_hint = _cfg.get("gdrive_root")
_init_theme = normalize_theme_name(_cfg.get("ui_theme", DEFAULT_THEME))

_resolved_file = None
if _cfg.get("rel_file"):
    _resolved_file = resolve_gdrive_path(_cfg["rel_file"], hint_root=_hint)
if not _resolved_file and _cfg.get("abs_file") and os.path.exists(_cfg["abs_file"]):
    _resolved_file = _cfg["abs_file"]
if not _resolved_file:
    _default_rel = os.path.join(_GDRIVE_REL_DIR, _GDRIVE_DEFAULT_FILE)
    _resolved_file = resolve_gdrive_path(_default_rel, hint_root=_hint)

_init_file = _resolved_file or ""

_resolved_outdir = None
if _cfg.get("rel_outdir"):
    _resolved_outdir = resolve_gdrive_path(_cfg["rel_outdir"], hint_root=_hint)
if not _resolved_outdir and _cfg.get("abs_outdir") and os.path.isdir(_cfg["abs_outdir"]):
    _resolved_outdir = _cfg["abs_outdir"]
if not _resolved_outdir and _init_file:
    _resolved_outdir = os.path.dirname(_init_file)

_init_outdir = _resolved_outdir or ""


# ═══════════════════════════════════════════════════════════════════════════
# Thread-safe signal bridge
# ═══════════════════════════════════════════════════════════════════════════
class WorkerSignals(QObject):
    log       = Signal(str, str)
    status    = Signal(str)
    current   = Signal(str)
    progress  = Signal(int, int)      # value, maximum
    duration  = Signal(str)
    finished  = Signal(int, str)      # error_count, error_msg


# ═══════════════════════════════════════════════════════════════════════════
# Generate checkbox tick icon (temp file used by QSS)
# ═══════════════════════════════════════════════════════════════════════════
_tmpmod = tempfile
_tick_path = os.path.join(_tmpmod.gettempdir(), "wt_extractor_tick.svg")
with open(_tick_path, "w") as _f:
    _f.write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" '
        'stroke="white" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
_tick_url = _tick_path.replace("\\", "/")

_arrow_path = os.path.join(_tmpmod.gettempdir(), "wt_extractor_arrow.svg")
with open(_arrow_path, "w") as _f:
    _f.write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
        '<path d="M2.5 4 L6 8.5 L9.5 4" fill="none" '
        'stroke="#4dc8e8" stroke-width="2.4" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
_arrow_url = _arrow_path.replace("\\", "/")

_spin_up_path = os.path.join(_tmpmod.gettempdir(), "wt_extractor_spin_up.svg")
with open(_spin_up_path, "w") as _f:
    _f.write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
        '<path d="M2.5 7.5 L6 4 L9.5 7.5" fill="none" '
        'stroke="#ffffff" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
_spin_up_url = _spin_up_path.replace("\\", "/")

_spin_down_path = os.path.join(_tmpmod.gettempdir(), "wt_extractor_spin_down.svg")
with open(_spin_down_path, "w") as _f:
    _f.write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
        '<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" '
        'stroke="#ffffff" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
_spin_down_url = _spin_down_path.replace("\\", "/")

THEME_ICON_DARK = "☾"
THEME_ICON_LIGHT = "☀"

# ═══════════════════════════════════════════════════════════════════════════
# QSS Stylesheet
# ═══════════════════════════════════════════════════════════════════════════
def load_base_stylesheet():
    with open(resource_path("app.qss"), "r", encoding="utf-8") as file_obj:
        stylesheet = file_obj.read()
    return (
        stylesheet
        .replace("__TICK_URL__", _tick_url)
        .replace("__ARROW_URL__", _arrow_url)
        .replace("__SPIN_UP_URL__", _spin_up_url)
        .replace("__SPIN_DOWN_URL__", _spin_down_url)
        .replace("__FONT_TITLE__", UI_FONT_TITLE)
        .replace("__FONT_BODY__", UI_FONT_BODY)
        .replace("__FONT_MONO__", UI_FONT_MONO)
    )


"""
/* ── Global ─────────────────────────────────────────── */
QMainWindow, QWidget#central {
    background-color: #0f1923;
}

QWidget#body {
    background-color: #0f1923;
}

/* ── Cards ──────────────────────────────────────────── */
QFrame[class="card"] {
    background-color: #162230;
    border: 1px solid #2a4055;
    border-radius: 10px;
}

/* ── Section titles ─────────────────────────────────── */
QLabel[class="section-title"] {
    color: #00b4d8;
    font-size: 14px;
    font-weight: 700;
    font-family: __FONT_TITLE__;
}

QLabel[class="section-accent"] {
    background-color: #00b4d8;
    border-radius: 2px;
}

/* ── Labels ─────────────────────────────────────────── */
QLabel {
    color: #d4dce6;
    font-family: __FONT_BODY__;
    font-size: 12px;
}

QLabel[class="dim"] {
    color: #8fa8be;
    font-size: 10px;
}

QLabel[class="file-name"] {
    color: #00b4d8;
    font-size: 13px;
    font-weight: 700;
}

QLabel[class="current-item"] {
    color: #ff6ec7;
    font-size: 15px;
    font-style: italic;
    font-family: __FONT_TITLE__;
}

QLabel[class="badge-ok"] {
    color: #b8ffda;
    font-size: 11px;
    font-weight: 700;
    background-color: #113427;
    border: 1px solid #1f7f58;
    border-radius: 10px;
    padding: 2px 8px;
}

QLabel[class="badge-warn"] {
    color: #ffe2b0;
    font-size: 11px;
    font-weight: 700;
    background-color: #3a2a10;
    border: 1px solid #9a6b21;
    border-radius: 10px;
    padding: 2px 8px;
}

/* ── Buttons (base) ─────────────────────────────────── */
QPushButton {
    background-color: #1c6f98;
    color: #ffffff;
    border: 1px solid #308cb8;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: __FONT_BODY__;
    font-size: 11px;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #2385b5;
    border: 1px solid #53bce9;
}
QPushButton:pressed {
    background-color: #145978;
    border: 1px solid #1c6f98;
    padding: 6px 14px 4px 14px;
}
QPushButton:disabled {
    background-color: #243646;
    color: #6f8598;
    border: 1px solid #31465a;
}

/* ── Start Processing ──────────────────────────────── */
QPushButton#btn-start {
    background-color: #00a86b;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 8px 24px;
    border-radius: 8px;
    border: 1px solid #33cc88;
}
QPushButton#btn-start:hover {
    background-color: #00cc82;
    border: 1px solid #55eea0;
}
QPushButton#btn-start:pressed {
    background-color: #007a4d;
    border: 1px solid #00a86b;
    padding: 8px 22px 6px 22px;
}

/* ── Abort ─────────────────────────────────────────── */
QPushButton#btn-abort {
    background-color: #d43535;
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 18px;
    border-radius: 8px;
    border: 1px solid #ee6666;
}
QPushButton#btn-abort:hover {
    background-color: #ee4c4c;
    border: 1px solid #ff8888;
}
QPushButton#btn-abort:pressed {
    background-color: #a82222;
    border: 1px solid #d43535;
    padding: 8px 16px 6px 16px;
}

/* ── Small buttons (Browse, Change, tab Select/Deselect) */
QPushButton[class="small-btn"] {
    background-color: #24465f;
    color: #cde8f5;
    font-size: 10px;
    padding: 5px 12px;
    border-radius: 7px;
    border: 1px solid #3f6e90;
}
QPushButton[class="small-btn"]:hover {
    background-color: #2d5776;
    border: 1px solid #4f89af;
}
QPushButton[class="small-btn"]:pressed {
    background-color: #1b3d53;
    border: 1px solid #2d5776;
    padding: 5px 10px 3px 10px;
}

/* ── Tabs ───────────────────────────────────────────── */
QTabWidget::pane {
    background-color: transparent;
    border: none;
    border-top: 2px solid #253545;
}
QTabBar {
    qproperty-drawBase: 0;
}
QTabBar::tab {
    background-color: #17283a;
    color: #728aa1;
    font-family: __FONT_TITLE__;
    font-size: 12px;
    font-weight: 700;
    padding: 9px 18px;
    border: 1px solid #253545;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #162230;
    color: #00f0a0;
    border: 1px solid #00d78d;
    border-bottom: 2px solid #162230;
}
QTabBar::tab:hover:!selected {
    background-color: #21384b;
    color: #c8d6e2;
    border-color: #4c6987;
}

/* ── Checkboxes ─────────────────────────────────────── */
QCheckBox {
    color: #d4dce6;
    font-family: __FONT_BODY__;
    font-size: 12px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #47617b;
    border-radius: 3px;
    background-color: #122133;
}
QCheckBox::indicator:checked {
    background-color: #00b4d8;
    border-color: #45dcf8;
    image: url(__TICK_URL__);
}
QCheckBox::indicator:hover {
    border-color: #00b4d8;
    background-color: #152a3a;
}
QCheckBox::indicator:checked:hover {
    background-color: #00d0f0;
    border-color: #33eeff;
}
QCheckBox:hover {
    color: #ffffff;
}

/* ── DateEdit ───────────────────────────────────────── */
QDateEdit {
    background-color: #1c2e3f;
    color: #d4dce6;
    border: 1px solid #3a5068;
    border-radius: 8px;
    padding: 6px 12px;
    font-family: __FONT_BODY__;
    font-size: 12px;
    min-width: 118px;
}
QDateEdit:focus {
    border-color: #00b4d8;
}
QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 32px;
    border-left: 1px solid #4d6a84;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #1a4a6a;
}
QDateEdit::drop-down:hover {
    background-color: #1b6090;
}
QDateEdit::down-arrow {
    image: url(__ARROW_URL__);
    width: 14px;
    height: 14px;
}

/* Calendar popup */
QCalendarWidget {
    background-color: #162838;
    border: 2px solid #3d8abf;
    border-radius: 10px;
    padding: 6px;
}
QCalendarWidget QToolButton {
    color: #ffffff;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-family: __FONT_BODY__;
    font-size: 13px;
    font-weight: 800;
}
QCalendarWidget QToolButton:hover { background-color: #1894c8; }
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    background-color: transparent;
    border: none;
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
    padding: 0px;
    qproperty-icon: none;
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {
    background-color: rgba(255, 255, 255, 50);
    border-radius: 6px;
    color: #70d8f0;
}
QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {
    color: #ffffff;
    background-color: transparent;
    padding: 4px 10px;
    font-size: 15px;
    font-weight: bold;
    border-radius: 6px;
}
QCalendarWidget QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget QToolButton#qt_calendar_yearbutton:hover {
    background-color: rgba(255, 255, 255, 50);
    color: #70d8f0;
}
QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator,
QCalendarWidget QToolButton#qt_calendar_yearbutton::menu-indicator {
    subcontrol-position: right center;
    width: 10px;
}
QCalendarWidget QMenu {
    background-color: #132230;
    color: #ffffff;
    border: 1px solid #3d8abf;
    font-size: 13px;
    padding: 4px;
}
QCalendarWidget QMenu::item {
    padding: 5px 20px;
    border-radius: 4px;
}
QCalendarWidget QMenu::item:selected {
    background-color: #00b4d8;
    color: #ffffff;
}
QCalendarWidget QSpinBox {
    background-color: #142333;
    color: #ffffff;
    border: 1px solid #3d8abf;
    border-radius: 4px;
    font-family: __FONT_BODY__;
    font-size: 13px;
    padding: 2px 4px;
}
QCalendarWidget QAbstractItemView {
    background-color: #111e2c;
    color: #e8f0f8;
    border: 1px solid #2a4a64;
    border-radius: 8px;
    selection-background-color: #00b4d8;
    selection-color: #ffffff;
    alternate-background-color: #162636;
    font-size: 13px;
    outline: none;
}
QCalendarWidget QAbstractItemView::item {
    padding: 4px;
    border-radius: 5px;
    min-width: 32px;
    min-height: 24px;
}
QCalendarWidget QAbstractItemView::item:hover {
    background-color: #1a5a80;
    color: #ffffff;
}
QCalendarWidget QAbstractItemView::item:selected {
    background-color: #00b4d8;
    color: #ffffff;
    font-weight: bold;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #0a6a9a;
    border: none;
    border-radius: 8px;
    margin-bottom: 4px;
    padding: 4px 6px;
    min-height: 34px;
}
/* Day-of-week header row */
QCalendarWidget QHeaderView::section {
    background-color: #1a3550;
    color: #6cc4e8;
    font-size: 12px;
    font-weight: bold;
    border: none;
    padding: 4px;
}
QPushButton#endDateTodayButton {
    margin: 6px 0 0 0;
    min-height: 28px;
}

/* ── Progress bar ───────────────────────────────────── */
QProgressBar {
    background-color: #1c2e3f;
    border: 1px solid #253545;
    border-radius: 7px;
    text-align: center;
    color: #d4dce6;
    font-family: __FONT_BODY__;
    font-size: 12px;
    font-weight: 700;
    min-height: 22px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00895e, stop:1 #00e676);
    border-radius: 5px;
}

/* ── Log text ───────────────────────────────────────── */
QTextEdit#log {
    background-color: #09131d;
    color: #d4dce6;
    border: 1px solid #29425a;
    border-radius: 10px;
    padding: 10px;
    font-family: __FONT_MONO__;
    font-size: 12px;
    selection-background-color: #0077b6;
}

/* ── Scrollbars ─────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #0f1923;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #3a5068;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background-color: #4a6a88; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background-color: #0f1923;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background-color: #3a5068;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover { background-color: #4a6a88; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Tooltip ────────────────────────────────────────── */
QToolTip {
    background-color: #253545;
    color: #d4dce6;
    border: 1px solid #3a5068;
    border-radius: 4px;
    padding: 4px 8px;
    font-family: __FONT_BODY__;
    font-size: 11px;
}
"""


DARK_STYLESHEET = load_base_stylesheet()


def build_light_stylesheet(base_stylesheet):
    replacements = [
        ("#ff6ec7", "#b13c86"),
        ("#ff9bd5", "#b13c86"),
        ("#b8ffda", "#176248"),
        ("#113427", "#e0f6eb"),
        ("#1f7f58", "#7dc5a4"),
        ("#ffe2b0", "#8d5d16"),
        ("#3a2a10", "#fff1d9"),
        ("#9a6b21", "#dfb15c"),
        ("#dff7ff", "#0a6080"),
        ("#f0c8a8", "#7a5538"),
        ("#e8a87c", "#8a6040"),
        ("#45dcf8", "#0088aa"),
        ("#00f0a0", "#0d986b"),
        ("#00d78d", "#1da878"),
        ("#1c3348", "#e4eff7"),
        ("#1e3650", "#dae9f3"),
        ("#0f1923", "#edf3f8"),
        ("#09131d", "#ffffff"),
        ("#162230", "#ffffff"),
        ("#17283a", "#dce8f1"),
        ("#1a2d3d", "#edf4f9"),
        ("#1b3d53", "#bcd7e7"),
        ("#1c2e3f", "#f7fbff"),
        ("#21384b", "#d5e5f0"),
        ("#243646", "#d6e2ea"),
        ("#24465f", "#dcecf7"),
        ("#253545", "#c4d4e0"),
        ("#29425a", "#c9d8e5"),
        ("#2a4055", "#c9d8e5"),
        ("#2d5776", "#c7deee"),
        ("#31465a", "#bccbd7"),
        ("#3a5068", "#a9becf"),
        ("#47617b", "#8ca6b9"),
        ("#4a6a88", "#96aec2"),
        ("#4c6987", "#9eb4c7"),
        ("#6f8598", "#5f7382"),
        ("#728aa1", "#3f586a"),
        ("#8fa8be", "#486173"),
        ("#c8d6e2", "#244052"),
        ("#cde8f5", "#1f455c"),
        ("#d4dce6", "#183548"),
        ("#122133", "#f7fbff"),
        ("#152a3a", "#edf5fa"),
    ]

    light_stylesheet = base_stylesheet
    for old, new in replacements:
        light_stylesheet = light_stylesheet.replace(old, new)
    return light_stylesheet


LIGHT_STYLESHEET = build_light_stylesheet(DARK_STYLESHEET)


def get_app_stylesheet(theme_name):
    return LIGHT_STYLESHEET if normalize_theme_name(theme_name) == "light" else DARK_STYLESHEET


# ═══════════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════════
class _UpdateEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback):
        super().__init__(self.EVENT_TYPE)
        self.callback = callback

def check_for_updates(callback):
    updater_check_for_updates(CURRENT_VERSION, callback)

class CombinerWidget(QWidget):
    """Premium launcher panel for the legacy RAW Combiner workflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.combiner_path = find_combiner_script()
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("combiner-root")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        hero_card = QFrame()
        hero_card.setProperty("class", "hero-card")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(10)

        eyebrow = QLabel("RAW LOGGER WORKFLOW")
        eyebrow.setProperty("class", "hero-eyebrow")
        hero_layout.addWidget(eyebrow)

        title = QLabel("RAW Combiner")
        title.setProperty("class", "hero-title")
        hero_layout.addWidget(title)

        summary = QLabel(
            "Batch-combine HOBO RAW files by site, keep updated outputs tidy, "
            "and launch the combiner tool from a cleaner HydroS workspace."
        )
        summary.setWordWrap(True)
        summary.setProperty("class", "hero-body")
        hero_layout.addWidget(summary)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        for text in ("Batch Combine", "Updated Outputs", "Site Workflow"):
            chip = QLabel(text)
            chip.setProperty("class", "hero-chip")
            chip_row.addWidget(chip)
        chip_row.addStretch()
        hero_layout.addLayout(chip_row)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(10)
        for value_text, label_text in (
            ("Batch-Ready", "Folder workflow"),
            ("Separate Tool", "Launch mode"),
            ("Legacy Safe", "Current setup"),
        ):
            metric_card = QFrame()
            metric_card.setProperty("class", "metric-card")
            metric_layout = QVBoxLayout(metric_card)
            metric_layout.setContentsMargins(14, 12, 14, 12)
            metric_layout.setSpacing(2)

            metric_value = QLabel(value_text)
            metric_value.setProperty("class", "metric-value")
            metric_layout.addWidget(metric_value)

            metric_label = QLabel(label_text)
            metric_label.setProperty("class", "metric-label")
            metric_layout.addWidget(metric_label)
            metric_layout.addStretch()

            metric_row.addWidget(metric_card, 1)
        hero_layout.addLayout(metric_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.btn_launch_combiner = QPushButton("Launch RAW Combiner")
        self.btn_launch_combiner.setProperty("class", "launch-btn")
        self.btn_launch_combiner.clicked.connect(self.launch_combiner)
        action_row.addWidget(self.btn_launch_combiner)

        self.btn_open_folder = QPushButton("Open Tool Folder")
        self.btn_open_folder.setProperty("class", "small-btn")
        self.btn_open_folder.clicked.connect(self.open_tool_folder)
        action_row.addWidget(self.btn_open_folder)
        action_row.addStretch()
        hero_layout.addLayout(action_row)

        self.status_label = QLabel()
        self.status_label.setProperty("class", "path-label")
        self.status_label.setWordWrap(True)
        hero_layout.addWidget(self.status_label)

        layout.addWidget(hero_card)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)

        workflow_card = QFrame()
        workflow_card.setProperty("class", "info-card")
        workflow_layout = QVBoxLayout(workflow_card)
        workflow_layout.setContentsMargins(16, 16, 16, 16)
        workflow_layout.setSpacing(8)
        workflow_title = QLabel("Workflow")
        workflow_title.setProperty("class", "info-title")
        workflow_layout.addWidget(workflow_title)
        workflow_text = QLabel(
            "1. Open the combiner tool.\n"
            "2. Select the RAW site folders you want.\n"
            "3. Process and combine outputs into each site's updated folder."
        )
        workflow_text.setProperty("class", "info-body")
        workflow_text.setWordWrap(True)
        workflow_layout.addWidget(workflow_text)
        workflow_layout.addStretch()
        detail_row.addWidget(workflow_card, 1)

        target_card = QFrame()
        target_card.setProperty("class", "info-card")
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(16, 16, 16, 16)
        target_layout.setSpacing(8)
        target_title = QLabel("Current Target")
        target_title.setProperty("class", "info-title")
        target_layout.addWidget(target_title)
        self.target_label = QLabel()
        self.target_label.setProperty("class", "info-body")
        self.target_label.setWordWrap(True)
        target_layout.addWidget(self.target_label)
        target_layout.addStretch()
        detail_row.addWidget(target_card, 1)

        layout.addLayout(detail_row)
        layout.addStretch()

        self._refresh_state()

    def _refresh_state(self):
        if self.combiner_path:
            self.target_label.setText(
                f"{os.path.basename(self.combiner_path)}\n\n{self.combiner_path}"
            )
            self.status_label.setText("Ready to launch the current RAW Combiner.")
            self.btn_launch_combiner.setEnabled(True)
        else:
            self.target_label.setText(
                "No RAW Combiner script found.\n\nExpected one of:\n- " + "\n- ".join(COMBINER_CANDIDATES)
            )
            self.status_label.setText(
                "Combiner script not found in the project root. Add it back to enable this launcher."
            )
            self.btn_launch_combiner.setEnabled(False)

    def launch_combiner(self):
        if not self.combiner_path:
            self._refresh_state()
            return

        try:
            if getattr(sys, "frozen", False):
                os.startfile(self.combiner_path)
            else:
                subprocess.Popen(
                    [sys.executable, self.combiner_path],
                    cwd=os.path.dirname(self.combiner_path),
                )
            self.status_label.setText("RAW Combiner launched in a separate window.")
        except Exception as exc:
            self.status_label.setText(f"Could not launch RAW Combiner: {exc}")

    def open_tool_folder(self):
        target = os.path.dirname(self.combiner_path) if self.combiner_path else project_root()
        try:
            os.startfile(target)
            self.status_label.setText("Opened the tool folder.")
        except Exception as exc:
            self.status_label.setText(f"Could not open the tool folder: {exc}")


class NeonBadge(QWidget):
    """Pill-shaped status badge with an animated neon glow when running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = "READY"
        self._fg = "#dff7ff"
        self._bg = "#184058"
        self._border = "#2c7ea1"
        self._glow_color = QColor("#2d8ab3")
        self._angle = 0
        self._animating = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(22)
        self.setMinimumWidth(60)

    def setText(self, text):
        self._text = text
        self.updateGeometry()
        self.update()

    def setNeonStyle(self, fg, bg, border, animate=False):
        self._fg = fg
        self._bg = bg
        self._border = border
        self._glow_color = QColor(border)
        if animate and not self._animating:
            self._animating = True
            self._timer.start(30)
        elif not animate and self._animating:
            self._animating = False
            self._timer.stop()
            self._angle = 0
        self.update()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def sizeHint(self):
        from PySide6.QtGui import QFontMetrics, QFont
        font = QFont(UI_FONT_BODY, 11)
        font.setBold(True)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(self._text) + 20
        return self.minimumSize() if w < self.minimumWidth() else type(self.minimumSize())(w, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2 - 1
        rect = QRectF(1, 1, w - 2, h - 2)

        # Background fill
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._bg))
        painter.drawRoundedRect(rect, radius, radius)

        if self._animating:
            # Neon glow border with conical gradient
            gradient = QConicalGradient(w / 2, h / 2, self._angle)
            glow = QColor(self._glow_color)
            glow_bright = QColor(glow)
            glow_bright.setAlpha(255)
            glow_dim = QColor(glow)
            glow_dim.setAlpha(40)
            gradient.setColorAt(0.0, glow_bright)
            gradient.setColorAt(0.15, glow_dim)
            gradient.setColorAt(0.85, glow_dim)
            gradient.setColorAt(1.0, glow_bright)

            pen = QPen(gradient, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)
        else:
            # Static border
            pen = QPen(QColor(self._border), 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        # Text
        from PySide6.QtGui import QFont
        font = QFont(UI_FONT_BODY, 11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._fg))
        painter.drawText(rect, Qt.AlignCenter, self._text)
        painter.end()


class WaveProgressBar(QProgressBar):
    """Progress bar with a single wave shimmer that travels across the filled area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wave_pos = 0.0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._wave_tick)
        self._animating = False
        self._wave_color = QColor(255, 255, 255, 60)

    def startWave(self):
        if not self._animating:
            self._animating = True
            self._wave_pos = 0.0
            self._wave_timer.start(30)

    def stopWave(self):
        if self._animating:
            self._animating = False
            self._wave_timer.stop()
            self._wave_pos = 0.0
            self.update()

    def _wave_tick(self):
        self._wave_pos += 0.06
        if self._wave_pos > 1.0:
            self._wave_pos = 0.0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._animating or self.maximum() == 0:
            return

        fraction = self.value() / self.maximum()
        if fraction <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_w = self.width() * fraction
        bar_h = self.height()

        wave_w = 40
        wave_center = self._wave_pos * bar_w

        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(wave_center - wave_w / 2, 0, wave_center + wave_w / 2, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, self._wave_color)
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setClipRect(QRectF(0, 0, bar_w, bar_h))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        radius = 5
        painter.drawRoundedRect(QRectF(0, 0, bar_w, bar_h), radius, radius)
        painter.end()


class ExtractorWidget(QWidget):
    """Manual Extractor UI — embeddable as a QWidget (tab or standalone)."""

    def __init__(self, parent=None, enable_updates=True):
        super().__init__(parent)

        self.full_filename = _init_file
        self.output_dir = _init_outdir
        self.theme_name = _init_theme
        self.enable_updates = enable_updates
        self.gdrive_roots = detect_google_drive_roots()
        self.stop_requested = False
        self.processing_running = False
        self.update_download_running = False
        self.progress_mode = "pipes"
        self.start_time = None
        self.site_checkboxes = {}
        self._status_badge_state = None
        self._log_entries = []
        self._section_accent_bars = []
        self._start_date_calendar_popup = None
        self._end_date_calendar_popup = None
        self._end_date_today_button = None
        self.signals = WorkerSignals()

        # Connect signals
        self.signals.log.connect(self._append_log)
        self.signals.status.connect(self._set_status)
        self.signals.current.connect(self._set_current)
        self.signals.progress.connect(self._set_progress)
        self.signals.duration.connect(self._set_duration)
        self.signals.finished.connect(self._on_finished)

        self._build_ui()
        self._apply_theme(self.theme_name, save=False)
        if self.enable_updates:
            cleanup_update_downloads()
        self._initial_log()

        if self.enable_updates:
            # Check for updates in background
            Thread(
                target=check_for_updates,
                args=(self._on_update_available,),
                daemon=True
            ).start()

    def _post_to_ui(self, callback):
        app = QApplication.instance()
        if app is not None:
            app.postEvent(self, _UpdateEvent(callback))

    def _on_update_available(self, latest_version):
        def _show():
            major = is_major_update(CURRENT_VERSION, latest_version)
            action = self._show_update_dialog(latest_version, major)
            if action == "update":
                self._start_update_download(latest_version, major)
            elif action == "browser":
                webbrowser.open(RELEASE_URL)
        self._post_to_ui(_show)

    def _show_update_dialog(self, latest_version, major):
        dlg = QDialog(self)
        dlg.setWindowTitle("Update Available")
        dlg.setMinimumWidth(430)
        dlg.setStyleSheet(self._dialog_stylesheet("#00b4d8"))

        layout = QVBoxLayout(dlg)

        if major:
            body = (
                f"Major update {latest_version} is available.\n"
                f"Current version: {CURRENT_VERSION}\n\n"
                "This is a major release and requires running the installer."
            )
            action_label = "Download Installer"
        else:
            body = (
                f"New version {latest_version} is available.\n"
                f"Current version: {CURRENT_VERSION}\n\n"
                "The app will download the update, restart, and apply it automatically."
            )
            action_label = "Update Now"

        msg = QLabel(body)
        msg.setObjectName("msg-body")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        yes_btn = QPushButton(action_label)
        browser_btn = QPushButton("Open Releases")
        no_btn = QPushButton("Later")

        result = {"value": "later"}

        def choose_update():
            result["value"] = "update"
            dlg.accept()

        def choose_browser():
            result["value"] = "browser"
            dlg.accept()

        yes_btn.clicked.connect(choose_update)
        browser_btn.clicked.connect(choose_browser)
        no_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(yes_btn)
        btn_row.addWidget(browser_btn)
        btn_row.addWidget(no_btn)
        layout.addLayout(btn_row)

        dlg.exec()
        return result["value"]

    def _start_update_download(self, latest_version, major):
        if self.update_download_running:
            self._show_msg("Update In Progress",
                          "An update is already downloading.", "warning")
            return

        self.update_download_running = True
        self.progress_mode = "download"
        self.signals.progress.emit(0, 100)

        if major:
            self.log(f"Major update {latest_version} detected. Downloading installer...", "info")
            self.signals.status.emit(f"Downloading installer v{latest_version}...")
            Thread(
                target=self._download_major_update,
                args=(latest_version,),
                daemon=True,
            ).start()
        else:
            self.log(f"Patch update {latest_version} detected. Downloading update...", "info")
            self.signals.status.emit(f"Downloading patch v{latest_version}...")
            Thread(
                target=self._download_patch_update,
                args=(latest_version,),
                daemon=True,
            ).start()

    # ── Patch update: download zip → extract → replace → restart ─────
    def _download_patch_update(self, latest_version):
        destination = None
        try:
            release_info = fetch_latest_release(latest_version)
            asset = select_zip_asset(release_info["assets"])
            if not asset:
                raise RuntimeError("No .zip patch asset found in the latest release.")

            download_dir = get_update_download_dir()
            cleanup_update_downloads()
            os.makedirs(download_dir, exist_ok=True)
            destination = make_unique_path(
                os.path.join(download_dir, asset.get("name") or "update.zip")
            )

            self.log(f"Downloading: {asset['name']}", "info")
            download_file(
                asset["browser_download_url"],
                destination,
                self.signals.status.emit,
                self.signals.progress.emit,
            )

            self.signals.status.emit("Extracting update...")
            self.log("Extracting update...", "info")
            extract_dir = os.path.join(download_dir, "_extracted")
            if os.path.exists(extract_dir):
                import shutil
                shutil.rmtree(extract_dir, ignore_errors=True)
            source_dir = extract_patch_zip(destination, extract_dir)

            install_dir = get_install_dir()
            script_path = write_patch_script(source_dir, install_dir)

            def _prompt_restart():
                self.update_download_running = False
                self.log("Update ready. Restarting to apply...", "ok")
                subprocess.Popen(
                    ["cmd", "/c", script_path],
                    creationflags=0x00000008,  # DETACHED_PROCESS
                )
                QApplication.instance().quit()

            self._post_to_ui(_prompt_restart)

        except Exception as exc:
            error_message = str(exc)
            if destination and os.path.exists(destination):
                try:
                    os.remove(destination)
                except OSError:
                    pass

            def _show_error():
                self.update_download_running = False
                self.log(f"Patch update failed: {error_message}", "err")
                self.signals.status.emit("Update failed. Opening releases page...")
                self._show_msg(
                    "Update Failed",
                    "Automatic update could not be completed.\n\n"
                    f"{error_message}\n\n"
                    "The GitHub releases page will open so you can download manually.",
                    "error",
                )
                webbrowser.open(RELEASE_URL)

            self._post_to_ui(_show_error)

    # ── Major update: download installer → user runs it ──────────────
    def _download_major_update(self, latest_version):
        destination = None
        try:
            release_info = fetch_latest_release(latest_version)
            asset = select_installer_asset(release_info["assets"])
            if not asset:
                raise RuntimeError("No installer asset (.exe or .msi) found in the latest release.")

            download_dir = get_update_download_dir()
            cleanup_update_downloads()
            os.makedirs(download_dir, exist_ok=True)
            destination = make_unique_path(
                os.path.join(download_dir, asset.get("name") or "setup.exe")
            )

            self.log(f"Downloading: {asset['name']}", "info")
            download_file(
                asset["browser_download_url"],
                destination,
                self.signals.status.emit,
                self.signals.progress.emit,
            )

            def _launch_silent_installer():
                self.update_download_running = False
                self.log("Installing major update...", "ok")
                subprocess.Popen(
                    [destination, "/SILENT", "/RESTARTAPPLICATIONS"],
                    creationflags=0x00000008,  # DETACHED_PROCESS
                )
                QApplication.instance().quit()

            self._post_to_ui(_launch_silent_installer)

        except Exception as exc:
            error_message = str(exc)
            if destination and os.path.exists(destination):
                try:
                    os.remove(destination)
                except OSError:
                    pass

            def _show_error():
                self.update_download_running = False
                self.log(f"Update download failed: {error_message}", "err")
                self.signals.status.emit("Update failed. Opening releases page...")
                self._show_msg(
                    "Update Download Failed",
                    "Automatic download could not be completed.\n\n"
                    f"{error_message}\n\n"
                    "The GitHub releases page will open so you can download manually.",
                    "error",
                )
                webbrowser.open(RELEASE_URL)

            self._post_to_ui(_show_error)

    
    # ── Build the entire UI ──────────────────────────────────────────────
    def _build_ui(self):
        self.setObjectName("central")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # (no header bar — version shown in window title)

        # ── Body (no scroll — fits in one screen) ────────────────────────
        body = QWidget()
        body.setObjectName("body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 6, 14, 6)
        body_layout.setSpacing(6)

        # ── Combined I/O + Date card ─────────────────────────────────────
        io_card = self._make_section("INPUT / OUTPUT", body_layout)
        io_inner = QGridLayout()
        io_inner.setHorizontalSpacing(10)
        io_inner.setVerticalSpacing(4)
        io_card.layout().addLayout(io_inner)

        # File row — full path as tooltip
        self.label_file = QLabel()
        self.label_file.setProperty("class", "file-name")
        self.label_file.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label_file.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: #18d0ff; font-family: {UI_FONT_TITLE};"
        )
        self.btn_browse = QPushButton("\U0001F4C2 Browse File")
        self.btn_browse.setProperty("class", "small-btn")
        self.btn_browse.setMinimumWidth(146)
        self.btn_browse.setToolTip("Browse the latest downloaded Google Sheet manual water table file.")
        self.btn_browse.clicked.connect(self.select_file)
        io_inner.addWidget(self._dim_label("Manual WT File", 110), 0, 0)
        io_inner.addWidget(self.label_file, 0, 1)
        io_inner.addWidget(self.btn_browse, 0, 2)

        # Output dir row
        self.label_outdir = QLabel()
        self.label_outdir.setProperty("class", "file-name")
        self.label_outdir.setStyleSheet(
            f"font-weight: 500; color: #8fdcff; font-size: 11px; font-family: {UI_FONT_BODY};"
        )
        self.label_outdir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.btn_outdir = QPushButton("\U0001F4C1 Change Folder")
        self.btn_outdir.setProperty("class", "small-btn")
        self.btn_outdir.setMinimumWidth(146)
        self.btn_outdir.clicked.connect(self.select_outdir)
        io_inner.addWidget(self._dim_label("Output Directory", 110), 1, 0)
        io_inner.addWidget(self.label_outdir, 1, 1)
        io_inner.addWidget(self.btn_outdir, 1, 2)

        # Date range row (inside same card)
        _today = date.today()
        _cfg_dates = load_config()
        _start = QDate(_today.year, 1, 1)
        _end = QDate(_today.year, _today.month, _today.day)
        if _cfg_dates.get("date_start"):
            try:
                ds = date.fromisoformat(_cfg_dates["date_start"])
                _start = QDate(ds.year, ds.month, ds.day)
            except ValueError:
                pass
        if _cfg_dates.get("date_end"):
            try:
                de = date.fromisoformat(_cfg_dates["date_end"])
                _end = QDate(de.year, de.month, de.day)
            except ValueError:
                pass

        io_inner.addWidget(self._dim_label("Date Range", 110), 2, 0)
        dt_row = QHBoxLayout()
        dt_row.setSpacing(8)
        dt_row.addWidget(QLabel("Start"))
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(_start)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setToolTip("First timestamp of the continuous 30-min grid")
        self._configure_date_calendar(self.date_start)
        self._install_start_date_popup_filter()
        dt_row.addWidget(self.date_start)
        dt_row.addSpacing(10)
        dt_row.addWidget(QLabel("End"))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(_end)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setToolTip("Last timestamp of the continuous 30-min grid")
        self._configure_date_calendar(self.date_end)
        dt_row.addWidget(self.date_end)
        dt_row.addStretch()
        io_inner.addLayout(dt_row, 2, 1, 1, 2)
        self._install_end_date_today_button()
        self.date_start.dateChanged.connect(self._persist_dates)
        self.date_end.dateChanged.connect(self._persist_dates)

        self._refresh_path_labels()

        # ── Pipe Selection card (WT_Marudi) ──────────────────────────────
        site_card = self._make_section("PIPE SELECTION", body_layout)
        site_inner = site_card.layout()
        site_inner.setSpacing(5)

        # Summary + Select/Clear row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.selected_label = QLabel("0 / 20 selected")
        self.selected_label.setStyleSheet(
            f"color: #ddf8ff; font-size: 11px; font-weight: 700; font-family: {UI_FONT_BODY}; "
            "background-color: #153548; border: 1px solid #266f8d; "
            "border-radius: 10px; padding: 2px 8px;"
        )
        top_row.addWidget(self.selected_label)
        top_row.addStretch()
        btn_sel = QPushButton("Select All")
        btn_sel.setProperty("class", "small-btn")
        btn_sel.clicked.connect(lambda: self.check_all("WT_Marudi"))
        top_row.addWidget(btn_sel)
        btn_clr = QPushButton("Clear All")
        btn_clr.setProperty("class", "small-btn")
        btn_clr.clicked.connect(lambda: self.uncheck_all("WT_Marudi"))
        top_row.addWidget(btn_clr)
        site_inner.addLayout(top_row)

        # Tabs per group
        self.site_checkboxes["WT_Marudi"] = {}
        self.group_checkboxes = {}
        self.tabs = QTabWidget()
        self.tabs.setObjectName("pipe-tabs")
        for group_name, pipes in PIPE_GROUPS:
            page = QWidget()
            page.setProperty("class", "tab-page")
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(10, 10, 10, 10)
            page_layout.setSpacing(8)

            # Select / Clear buttons per tab
            btn_row = QHBoxLayout()
            sa = QPushButton("Select Tab")
            sa.setProperty("class", "small-btn")
            sa.clicked.connect(lambda checked=False, g=group_name: self._check_group(g, True))
            btn_row.addWidget(sa)
            da = QPushButton("Clear Tab")
            da.setProperty("class", "small-btn")
            da.clicked.connect(lambda checked=False, g=group_name: self._check_group(g, False))
            btn_row.addWidget(da)
            btn_row.addStretch()
            page_layout.addLayout(btn_row)

            # Checkboxes grid
            grid = QGridLayout()
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(10)
            grid.setContentsMargins(0, 2, 0, 0)
            self.group_checkboxes[group_name] = {}
            cols = 5
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            for i, pipe in enumerate(pipes):
                cb = QCheckBox(pipe)
                cb.stateChanged.connect(self._update_selection_summary)
                grid.addWidget(cb, i // cols, i % cols)
                self.site_checkboxes["WT_Marudi"][pipe] = cb
                self.group_checkboxes[group_name][pipe] = cb
            page_layout.addLayout(grid)
            page_layout.addStretch()

            self.tabs.addTab(page, group_name)

        self.tabs.currentChanged.connect(self._update_selection_summary)
        site_inner.addWidget(self.tabs)

        self._update_selection_summary()

        # ── Action buttons ───────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()

        self.btn_start = QPushButton("▶ Start Processing")
        self.btn_start.setObjectName("btn-start")
        self.btn_start.setToolTip("Start extracting the selected site and pipe data.")
        self.btn_start.clicked.connect(self.start_processing)
        action_row.addWidget(self.btn_start)

        self.btn_abort = QPushButton("■ Abort")
        self.btn_abort.setObjectName("btn-abort")
        self.btn_abort.setToolTip("Abort is enabled only while processing is running.")
        self.btn_abort.clicked.connect(self.abort_processing)
        action_row.addWidget(self.btn_abort)
        site_inner.addLayout(action_row)

        # ── Processing Status card ──────────────────────────────────────
        prog_card = self._make_section("PROCESSING STATUS", body_layout)
        prog_inner = prog_card.layout()
        prog_inner.setContentsMargins(14, 6, 14, 6)
        prog_inner.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.status_badge = NeonBadge()
        self.status_badge.setNeonStyle("#dff7ff", "#184058", "#2c7ea1")
        status_row.addWidget(self.status_badge)
        self.status_label = QLabel("Ready to process selected pipes.")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: #d4dce6; font-family: {UI_FONT_BODY};"
        )
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.duration_label = QLabel("Duration: 0 sec")
        self.duration_label.setProperty("class", "dim")
        status_row.addWidget(self.duration_label)
        prog_inner.addLayout(status_row)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.progress_bar = WaveProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m pipes")
        self.progress_bar.setFixedHeight(22)
        prog_row.addWidget(self.progress_bar, 1)
        self.current_item_label = QLabel("No active task")
        self.current_item_label.setProperty("class", "current-item")
        self.current_item_label.setStyleSheet(
            f"font-size: 11px; font-style: italic; color: #ff9bd5; font-family: {UI_FONT_TITLE};"
        )
        prog_row.addWidget(self.current_item_label)
        prog_inner.addLayout(prog_row)

        # ── Log ──────────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        accent_bar = QLabel()
        accent_bar.setFixedSize(4, 14)
        self._section_accent_bars.append(accent_bar)
        log_header.addWidget(accent_bar)
        lt = QLabel("PROCESSING LOG")
        lt.setProperty("class", "section-title")
        log_header.addWidget(lt)
        log_header.addStretch()
        btn_clear = QPushButton("🧹 Clear Log")
        btn_clear.setProperty("class", "small-btn")
        btn_clear.setStyleSheet(
            f"font-size: 12px; font-weight: 700; padding: 6px 14px; font-family: {UI_FONT_BODY};"
        )
        btn_clear.clicked.connect(self.clear_log)
        log_header.addWidget(btn_clear)
        body_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("log")
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(60)
        self.log_text.setMaximumHeight(320)
        body_layout.addWidget(self.log_text, 1)

        root_layout.addWidget(body, 1)
        self._apply_button_styles()
        self._set_processing_controls(False)

    # ── UI helpers ───────────────────────────────────────────────────────
    def _button_qss(self, normal_bg, hover_bg, pressed_bg, border_color,
                    hover_border, pressed_border, font_size, padding,
                    disabled_bg="#243646", disabled_border="#31465a",
                    disabled_text="#6f8598"):
        return f"""
            QPushButton {{
                background-color: {normal_bg};
                color: #ffffff;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-family: {UI_FONT_BODY};
                font-size: {font_size}px;
                font-weight: bold;
                padding: {padding};
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border: 1px solid {hover_border};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg};
                border: 1px solid {pressed_border};
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg};
                color: {disabled_text};
                border: 1px solid {disabled_border};
            }}
        """
    def event(self, event):
        if event.type() == _UpdateEvent.EVENT_TYPE:
            event.callback()
            return True
        return super().event(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            if obj is self._start_date_calendar_popup:
                self._resize_start_date_calendar()
            elif obj is self._end_date_calendar_popup:
                self._resize_end_date_calendar_popup()
        return super().eventFilter(obj, event)

    def _theme_colors(self):
        return THEME_COLORS[self.theme_name]

    def _pill_qss(self, fg, bg, border):
        return (
            f"color: {fg}; font-size: 11px; font-weight: 700; font-family: {UI_FONT_BODY}; "
            f"background-color: {bg}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 2px 8px;"
        )

    def _dialog_stylesheet(self, accent):
        colors = self._theme_colors()
        return f"""
            QDialog {{
                background-color: {colors['dialog_bg']};
                border: 1px solid {colors['dialog_border']};
            }}
            QLabel#msg-icon {{
                color: {accent};
                font-size: 28px;
                font-weight: bold;
            }}
            QLabel#msg-title {{
                color: {colors['dialog_title']};
                font-size: 15px;
                font-weight: 700;
                font-family: {UI_FONT_TITLE};
            }}
            QLabel#msg-body {{
                color: {colors['dialog_text']};
                font-size: 13px;
                font-family: {UI_FONT_BODY};
            }}
            QPushButton {{
                background-color: {accent};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-family: {UI_FONT_BODY};
                font-size: 12px;
                font-weight: 700;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {colors['dialog_hover_bg']};
                color: {colors['dialog_hover_text']};
            }}
            QPushButton:pressed {{
                background-color: {colors['dialog_pressed_bg']};
                color: {colors['dialog_pressed_text']};
            }}
        """

    def _theme_toggle_button_qss(self):
        is_dark = self.theme_name == "dark"
        border = "#ffffff" if is_dark else "#000000"
        fg = "#ffffff" if is_dark else "#000000"
        return f"""
            QPushButton {{
                color: {fg};
                background-color: transparent;
                border: 1px solid {border};
                border-radius: 10px;
                padding: 4px 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                border-color: {'#45dcf8' if is_dark else '#0088aa'};
            }}
            QPushButton:pressed {{
                background-color: transparent;
            }}
        """

    def _update_theme_toggle_buttons(self):
        if not hasattr(self, "btn_theme_toggle"):
            return

        is_dark = self.theme_name == "dark"
        self.btn_theme_toggle.setText(THEME_ICON_LIGHT if is_dark else THEME_ICON_DARK)
        self.btn_theme_toggle.setStyleSheet(self._theme_toggle_button_qss())

    def _apply_theme(self, theme_name, save=True):
        self.theme_name = normalize_theme_name(theme_name)
        colors = self._theme_colors()

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(get_app_stylesheet(self.theme_name))

        if hasattr(self, "label_file"):
            self.label_file.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {colors['file_name']}; font-family: {UI_FONT_TITLE};"
            )
        if hasattr(self, "label_outdir"):
            self.label_outdir.setStyleSheet(
                f"font-weight: 500; color: {colors['outdir']}; font-size: 11px; font-family: {UI_FONT_BODY};"
            )
        if hasattr(self, "status_label"):
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {colors['status_text']}; font-family: {UI_FONT_BODY};"
            )
        if hasattr(self, "current_item_label"):
            self.current_item_label.setStyleSheet(
                f"font-size: 11px; font-style: italic; color: {colors['current_item']}; font-family: {UI_FONT_TITLE};"
            )

        for accent_bar in self._section_accent_bars:
            accent_bar.setStyleSheet(
                f"background-color: {colors['section_accent']}; border-radius: 2px;"
            )

        self._update_theme_toggle_buttons()
        self._apply_button_styles()

        if hasattr(self, "selected_label"):
            self._update_selection_summary()
        if self._status_badge_state:
            self._set_status_badge(*self._status_badge_state)
        elif hasattr(self, "status_badge"):
            self._set_status_badge("READY", *colors["status_ready"])

        if hasattr(self, "log_text") and self._log_entries:
            self._recolor_log()

        if save:
            cfg = load_config()
            cfg["ui_theme"] = self.theme_name
            save_config(cfg)

    def _switch_theme(self, theme_name):
        self._apply_theme(theme_name)

    def _toggle_theme(self):
        self._apply_theme("light" if self.theme_name == "dark" else "dark")

    def _apply_button_styles(self):
        colors = self._theme_colors()
        self.btn_start.setStyleSheet(self._button_qss(
            "#00a86b", "#00cc82", "#007a4d",
            "#33cc88", "#55eea0", "#00a86b",
            12, "7px 28px",
            colors["start_disabled_bg"], colors["start_disabled_border"], colors["start_disabled_text"]
        ))
        self.btn_abort.setStyleSheet(self._button_qss(
            "#d43535", "#ee4c4c", "#a82222",
            "#ee6666", "#ff8888", "#d43535",
            11, "7px 20px",
            colors["abort_disabled_bg"], colors["abort_disabled_border"], colors["abort_disabled_text"]
        ))

    def _compact_path(self, path, max_len=52):
        if not path:
            return "(none)"
        path = os.path.normpath(path)
        if len(path) <= max_len:
            return path
        parts = path.split(os.sep)
        if len(parts) <= 2:
            return path[:max_len - 3] + "..."
        return os.sep.join([parts[0], "...", parts[-2], parts[-1]])

    def _refresh_path_labels(self):
        file_text = self._compact_path(self.full_filename, 60) if self.full_filename else "(no file selected)"
        out_text = self._compact_path(self.output_dir, 60) if self.output_dir else "(no directory selected)"
        self.label_file.setText(file_text)
        self.label_file.setToolTip(self.full_filename or "(no file selected)")
        self.label_outdir.setText(out_text)
        self.label_outdir.setToolTip(self.output_dir or "(no directory selected)")

    def _check_group(self, group_name, state):
        for cb in self.group_checkboxes.get(group_name, {}).values():
            cb.setChecked(state)

    def _update_selection_summary(self, *_):
        # Update tab labels with counts
        for idx, (group_name, _) in enumerate(PIPE_GROUPS):
            grp_cbs = self.group_checkboxes.get(group_name, {})
            grp_total = len(grp_cbs)
            grp_sel = sum(1 for cb in grp_cbs.values() if cb.isChecked())
            self.tabs.setTabText(idx, f"{group_name} ({grp_sel}/{grp_total})")

        # Total count
        cbs = self.site_checkboxes.get("WT_Marudi", {})
        total = len(cbs)
        selected = sum(1 for cb in cbs.values() if cb.isChecked())
        self.selected_label.setText(f"{selected} / {total} selected")
        colors = self._theme_colors()
        if selected:
            self.selected_label.setStyleSheet(self._pill_qss(*colors["selected_active"]))
        else:
            self.selected_label.setStyleSheet(self._pill_qss(*colors["selected_idle"]))

    def _set_status_badge(self, text, bg, border, fg="#dff7ff"):
        self._status_badge_state = (text, bg, border, fg)
        self.status_badge.setText(text)
        animate = text in ("RUNNING", "STOPPING")
        self.status_badge.setNeonStyle(fg, bg, border, animate=animate)

    def _set_processing_controls(self, running):
        self.btn_abort.setEnabled(running)
        self.btn_start.setEnabled(not running)
        self.btn_browse.setEnabled(not running)
        self.btn_outdir.setEnabled(not running)
        self.tabs.setEnabled(not running)
        for cb in self.site_checkboxes.get("WT_Marudi", {}).values():
            cb.setEnabled(not running)
        if running:
            self.progress_bar.startWave()
        else:
            self.progress_bar.stopWave()

    def _dim_label(self, text, width=120):
        lbl = QLabel(text)
        lbl.setProperty("class", "dim")
        lbl.setFixedWidth(width)
        return lbl

    def _make_section(self, title, parent_layout):
        # Section header
        hdr = QHBoxLayout()
        accent_bar = QLabel()
        accent_bar.setFixedSize(4, 14)
        accent_bar.setProperty("class", "section-accent")
        self._section_accent_bars.append(accent_bar)
        hdr.addWidget(accent_bar)
        lbl = QLabel(title)
        lbl.setProperty("class", "section-title")
        hdr.addWidget(lbl)
        hdr.addStretch()
        parent_layout.addLayout(hdr)

        # Card frame
        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(6)
        parent_layout.addWidget(card)
        return card

    # ── Custom styled message dialog ────────────────────────────────────
    _MSG_ICONS = {"info": "#00b4d8", "warning": "#ffb347", "error": "#ff5252"}

    def _show_msg(self, title, message, level="info"):
        """Show a themed message dialog (replaces QMessageBox)."""
        accent = self._MSG_ICONS.get(level, "#00b4d8")
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(self._dialog_stylesheet(accent))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Icon + title row
        top = QHBoxLayout()
        icon_map = {"info": "\u2139", "warning": "\u26A0", "error": "\u2716"}
        icon_lbl = QLabel(icon_map.get(level, "\u2139"))
        icon_lbl.setObjectName("msg-icon")
        top.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("msg-title")
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        # Body
        body_lbl = QLabel(message)
        body_lbl.setObjectName("msg-body")
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)

        layout.addSpacing(8)

        # OK button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        dlg.exec()

    # ── Log ──────────────────────────────────────────────────────────────
    def _append_log(self, msg, color="white"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_entries.append((timestamp, msg, color))
        fmt = QTextCharFormat()
        log_colors = self._theme_colors()["log_colors"]
        fmt.setForeground(QColor(log_colors.get(color, log_colors["white"])))
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f"[{timestamp}] {msg}\n", fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def _recolor_log(self):
        """Re-render all log entries with the current theme colors."""
        log_colors = self._theme_colors()["log_colors"]
        self.log_text.clear()
        cursor = self.log_text.textCursor()
        for timestamp, msg, color in self._log_entries:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(log_colors.get(color, log_colors["white"])))
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(f"[{timestamp}] {msg}\n", fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def log(self, msg, color="white"):
        self.signals.log.emit(msg, color)

    def clear_log(self):
        self.log_text.clear()
        self._log_entries.clear()

    # ── Slot helpers ─────────────────────────────────────────────────────
    def _set_status(self, text):
        self.status_label.setText(text)

    def _set_current(self, text):
        self.current_item_label.setText(text or "No active task")

    def _set_progress(self, value, maximum):
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        if self.progress_mode == "download":
            self.progress_bar.setFormat(f"{value}% downloaded")
        else:
            self.progress_bar.setFormat(f"{value} / {maximum} pipe{'s' if maximum != 1 else ''}")

    def _set_duration(self, text):
        self.duration_label.setText(text)

    def _on_finished(self, error_count, error_msg):
        self.processing_running = False
        self._set_processing_controls(False)
        self.current_item_label.setText("No active task")
        if self.stop_requested:
            self._set_status_badge("ABORTED", "#4a3018", "#ab7a2f", "#ffe2b0")
            self.status_label.setText("Processing aborted.")
        elif error_count:
            self._set_status_badge("DONE WITH ERRORS", "#4a281d", "#b8644d", "#ffd1c2")
            self.status_label.setText(f"Done with {error_count} error(s). See log for details.")
            self._show_msg("Completed with Errors",
                          f"{error_count} pipe(s) had errors:\n\n{error_msg}", "warning")
        else:
            self._set_status_badge("SUCCESS", "#143d2d", "#2a9f67", "#d9ffe8")
            self.status_label.setText("All selected pipes processed successfully.")
            self.log("All done!", "ok")

    # ── Initial log ──────────────────────────────────────────────────────
    def _initial_log(self):
        self._append_log(f"{WINDOW_TITLE} v{CURRENT_VERSION} ready.", "info")
        gdrive_roots = detect_google_drive_roots()
        if gdrive_roots:
            self._append_log(f"Google Drive found: {gdrive_roots[0]}", "ok")
        else:
            self._append_log("Google Drive not detected — use Browse to select files manually.", "warn")
        if self.full_filename and os.path.exists(self.full_filename):
            self._append_log(f"Input file : {self.full_filename}", "white")
        else:
            self._append_log("No input file selected — click Browse to choose one.", "warn")
        self._append_log(f"Output dir : {self.output_dir or '(none)'}", "white")

    # ── File / dir selection ─────────────────────────────────────────────
    def _persist_paths(self):
        cfg = load_config()
        rel, gdroot = to_gdrive_relative(self.full_filename)
        if rel:
            cfg["rel_file"] = rel
            cfg["gdrive_root"] = gdroot
        else:
            cfg.pop("rel_file", None)
        cfg["abs_file"] = self.full_filename
        rel_out, gdroot_out = to_gdrive_relative(self.output_dir)
        if rel_out:
            cfg["rel_outdir"] = rel_out
            cfg["gdrive_root"] = gdroot_out
        else:
            cfg.pop("rel_outdir", None)
        cfg["abs_outdir"] = self.output_dir
        save_config(cfg)

    def _persist_dates(self):
        cfg = load_config()
        ds = self.date_start.date()
        de = self.date_end.date()
        cfg["date_start"] = f"{ds.year():04d}-{ds.month():02d}-{ds.day():02d}"
        cfg["date_end"] = f"{de.year():04d}-{de.month():02d}-{de.day():02d}"
        save_config(cfg)

    def _configure_date_calendar(self, date_edit):
        calendar = date_edit.calendarWidget()
        if calendar is None:
            return

        calendar.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        calendar.setMinimumWidth(CALENDAR_POPUP_WIDTH)

        # ── Restore red weekend day colors ──
        weekend_fmt = QTextCharFormat()
        weekend_fmt.setForeground(QColor("#ff4444"))
        calendar.setWeekdayTextFormat(Qt.Saturday, weekend_fmt)
        calendar.setWeekdayTextFormat(Qt.Sunday, weekend_fmt)

        weekday_fmt = QTextCharFormat()
        weekday_fmt.setForeground(QColor("#e0e8f0"))
        for d in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Friday):
            calendar.setWeekdayTextFormat(d, weekday_fmt)

        # ── Ensure enough height for 6-row months ──
        calendar.setMinimumHeight(270)

        # ── Replace arrow icons with text arrows for clarity ──
        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if prev_btn is not None:
            prev_btn.setIcon(QIcon())
            prev_btn.setText("\u25C0")
        if next_btn is not None:
            next_btn.setIcon(QIcon())
            next_btn.setText("\u25B6")

        # ── Fix header row styling via table view ──
        table_view = calendar.findChild(QTableView)
        if table_view is not None:
            table_view.setMouseTracking(True)
            table_view.setMinimumWidth(CALENDAR_POPUP_WIDTH)
            header = table_view.horizontalHeader()
            if header is not None:
                header.setStyleSheet(
                    "QHeaderView::section {"
                    "  background-color: #1a3550;"
                    "  color: #6cc4e8;"
                    "  font-size: 12px;"
                    "  font-weight: bold;"
                    "  border: none;"
                    "  padding: 5px 2px;"
                    "}"
                )
                header.setMinimumHeight(28)
            viewport = table_view.viewport()
            if viewport is not None:
                viewport.setMouseTracking(True)

        popup = calendar.window()
        if popup is not None and popup is not calendar:
            popup.setStyleSheet("background-color: #162230;")
            popup.setMinimumWidth(CALENDAR_POPUP_WIDTH)

    def _install_start_date_popup_filter(self):
        calendar = self.date_start.calendarWidget()
        if calendar is None:
            return
        popup = calendar.window()
        if popup is not None and popup is not calendar:
            self._start_date_calendar_popup = popup
            popup.installEventFilter(self)
        self._resize_start_date_calendar()

    def _resize_start_date_calendar(self):
        """Match start calendar size to end calendar (minus Today button)."""
        calendar = self.date_start.calendarWidget()
        if calendar is None:
            return
        cal_layout = calendar.layout()
        if cal_layout is not None:
            cal_layout.activate()
        table_view = calendar.findChild(QTableView)
        extra_row_height = table_view.rowHeight(0) if table_view is not None else 24
        target_size = calendar.sizeHint().expandedTo(calendar.minimumSizeHint())
        target_size.setWidth(max(target_size.width(), CALENDAR_POPUP_WIDTH))
        target_size.setHeight(target_size.height() + extra_row_height + 8)
        calendar.setFixedSize(target_size)
        popup = calendar.window()
        if popup is not None and popup is not calendar:
            popup.setStyleSheet("background-color: #162230;")
            popup.setMinimumWidth(target_size.width())
            popup.adjustSize()
            popup.resize(popup.sizeHint())

    def _install_end_date_today_button(self):
        calendar = self.date_end.calendarWidget()
        if calendar is None:
            return
        if calendar.findChild(QPushButton, "endDateTodayButton") is not None:
            return
        calendar_layout = calendar.layout()
        if calendar_layout is None:
            return

        today_btn = QPushButton("Today", calendar)
        today_btn.setObjectName("endDateTodayButton")
        today_btn.setProperty("class", "small-btn")
        today_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        today_btn.clicked.connect(self._set_end_date_to_today)
        calendar_layout.addWidget(today_btn)
        self._end_date_today_button = today_btn

        popup = calendar.window()
        if popup is not None and popup is not calendar:
            self._end_date_calendar_popup = popup
            popup.installEventFilter(self)

        self._resize_end_date_calendar_popup()

    def _resize_end_date_calendar_popup(self):
        calendar = self.date_end.calendarWidget()
        if calendar is None or self._end_date_today_button is None:
            return

        calendar_layout = calendar.layout()
        if calendar_layout is not None:
            calendar_layout.activate()
        table_view = calendar.findChild(QTableView)
        extra_row_height = table_view.rowHeight(0) if table_view is not None else 24
        button_height = self._end_date_today_button.sizeHint().height()
        target_size = calendar.sizeHint().expandedTo(calendar.minimumSizeHint())
        target_size.setWidth(max(target_size.width(), CALENDAR_POPUP_WIDTH))
        target_height = target_size.height() + button_height + extra_row_height + 8
        target_size.setHeight(target_height)
        calendar.setFixedSize(target_size)

        popup = calendar.window()
        if popup is not None and popup is not calendar:
            popup.setStyleSheet("background-color: #162230;")
            popup.setMinimumWidth(target_size.width())
            popup.adjustSize()
            popup.resize(popup.sizeHint())

    def _set_end_date_to_today(self):
        self.date_end.setDate(QDate.currentDate())
        calendar = self.date_end.calendarWidget()
        popup = calendar.window() if calendar is not None else None
        if popup is not None:
            popup.hide()

    def select_file(self):
        init_dir = os.path.dirname(self.full_filename) if self.full_filename and os.path.exists(self.full_filename) else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Manual WT Excel File", init_dir,
            "Excel files (*.xlsx);;All files (*.*)")
        if not path:
            return
        self.full_filename = path
        self.output_dir = os.path.dirname(path)
        self._refresh_path_labels()
        self._persist_paths()

    def select_outdir(self):
        init_dir = self.output_dir if self.output_dir and os.path.isdir(self.output_dir) else ""
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory", init_dir)
        if not path:
            return
        self.output_dir = path
        self._refresh_path_labels()
        self._persist_paths()

    # ── Checkbox helpers ─────────────────────────────────────────────────
    def check_all(self, site):
        for cb in self.site_checkboxes[site].values():
            cb.setChecked(True)
        self._update_selection_summary()

    def uncheck_all(self, site):
        for cb in self.site_checkboxes[site].values():
            cb.setChecked(False)
        self._update_selection_summary()

    # ── Processing ───────────────────────────────────────────────────────
    def start_processing(self):
        """Validate on the main thread, then spawn worker if OK."""
        if self.processing_running:
            return
        self.progress_mode = "pipes"

        # ── Validation (main thread → safe to show dialogs) ──
        if not self.full_filename or not os.path.exists(self.full_filename):
            self._show_msg("No Input File",
                          "Please select a valid Manual WT Excel file before processing.", "error")
            return
        if not self.output_dir or not os.path.isdir(self.output_dir):
            self._show_msg("No Output Directory",
                          "Please select a valid output directory before processing.", "error")
            return

        selections = [
            (site, pipe)
            for site, chks in self.site_checkboxes.items()
            for pipe, cb in chks.items()
            if cb.isChecked()
        ]
        if not selections:
            self._show_msg("Selection Required",
                          "Please select at least one pipe before starting.", "warning")
            return

        try:
            ds = self.date_start.date()
            de = self.date_end.date()
            date_start = pd.Timestamp(ds.year(), ds.month(), ds.day())
            date_end   = pd.Timestamp(de.year(), de.month(), de.day())
        except Exception:
            self._show_msg("Invalid Date",
                          "Please enter valid dates in YYYY-MM-DD format.", "error")
            return

        # ── Save dates to config ──
        self._persist_dates()

        # ── All OK — start worker ──
        self.start_time = datetime.now()
        self.processing_running = True
        self.stop_requested = False
        self._set_processing_controls(True)
        self._set_status_badge("RUNNING", "#14384f", "#2d8ab3")
        self.current_item_label.setText("Preparing worker...")
        self.signals.progress.emit(0, len(selections))
        self.signals.status.emit("Starting processing...")

        Thread(target=self._process_worker,
               args=(selections, date_start, date_end),
               daemon=True).start()

    def abort_processing(self):
        if not self.processing_running:
            return
        self.stop_requested = True
        self._set_status_badge("STOPPING", "#4a3018", "#ab7a2f", "#ffe2b0")
        self.status_label.setText("Abort requested. Finishing current step...")
        self.log("Abort requested by user.", "warn")

    def _process_worker(self, selections, date_start, date_end):
        self.signals.progress.emit(0, len(selections))
        self.signals.status.emit("Starting processing...")
        self.log(f"Processing {len(selections)} pipe(s)  |  "
                 f"{date_start.date()} -> {date_end.date()}", "info")

        errors = []

        for idx, (site, pipe) in enumerate(selections, 1):
            if self.stop_requested:
                self.signals.status.emit("Processing aborted.")
                self.log("Processing aborted.", "warn")
                break

            self.signals.duration.emit(
                format_duration((datetime.now() - self.start_time).total_seconds())
            )

            self.signals.current.emit(f"{site} -> {pipe}")
            self.signals.status.emit(f"Processing: {site} -> {pipe}  ({idx}/{len(selections)})")
            self.log(f"Processing: {pipe}")

            try:
                process_pipe(
                    self.full_filename,
                    self.output_dir,
                    site,
                    pipe,
                    date_start,
                    date_end,
                )
                self.log(f"{pipe} -> saved", "ok")

            except Exception as exc:
                errors.append((site, pipe, str(exc)))
                self.log(f"  FAIL  {pipe}  ERROR: {exc}", "err")

            self.signals.progress.emit(idx, len(selections))

        # Final duration
        self.signals.duration.emit(
            format_duration((datetime.now() - self.start_time).total_seconds())
        )

        err_msg = "\n".join(f"{s}/{p}: {e}" for s, p, e in errors)
        self.signals.finished.emit(len(errors), err_msg)


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════
INITIAL_THEME = _init_theme
