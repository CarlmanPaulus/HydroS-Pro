"""HydroS — RAW Files Combiner – PySide6 main window."""

import os
import sys
import tempfile
import time
from datetime import datetime
from threading import Thread

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QProgressBar, QTextEdit, QFrame,
    QGridLayout, QSizePolicy, QTabWidget, QFileDialog,
)
from PySide6.QtCore import Signal, QObject, Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QIcon, QPainter, QPen, QConicalGradient

from .config import SITE_GROUPS, build_directories, get_initial_site_paths, save_site_paths
from .processing import format_duration, process_directory

APP_ID = "hydros.rawcombiner"
WINDOW_TITLE = "HydroS — RAW Combiner"
CURRENT_VERSION = "3.0.7"

UI_FONT_TITLE = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Arial"'
UI_FONT_BODY = '"Segoe UI Variable Text", "Segoe UI", "Arial"'
UI_FONT_MONO = '"Cascadia Mono", "JetBrains Mono", "Consolas", "Courier New"'

THEME_COLORS = {
    "dark": {
        "file_name": "#18d0ff",
        "status_text": "#d4dce6",
        "current_item": "#ff9bd5",
        "section_accent": "#00b4d8",
        "selected_idle": ("#ddf8ff", "#153548", "#266f8d"),
        "selected_active": ("#e9fff4", "#154533", "#2da56b"),
        "status_ready": ("#dff7ff", "#184058", "#2c7ea1"),
        "start_disabled_bg": "#243746",
        "start_disabled_border": "#31475a",
        "start_disabled_text": "#6f8598",
        "abort_disabled_bg": "#332426",
        "abort_disabled_border": "#4d3135",
        "abort_disabled_text": "#967f82",
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
        "status_text": "#18384c",
        "current_item": "#962d73",
        "section_accent": "#00a4cc",
        "selected_idle": ("#153f58", "#deeff8", "#74a8c4"),
        "selected_active": ("#14553f", "#e0f6eb", "#68b592"),
        "status_ready": ("#153f58", "#dfeff8", "#78aac6"),
        "start_disabled_bg": "#d6e2ea",
        "start_disabled_border": "#bccbd7",
        "start_disabled_text": "#5f7382",
        "abort_disabled_bg": "#ead7da",
        "abort_disabled_border": "#d7bcc0",
        "abort_disabled_text": "#88686e",
        "log_colors": {
            "info": "#086e9d",
            "ok": "#0b7648",
            "warn": "#8e5809",
            "err": "#ad3030",
            "white": "#183548",
        },
    },
}
DEFAULT_THEME = "dark"


def resource_path(filename):
    """Return correct path whether running as script or PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


# ═══════════════════════════════════════════════════════════════════════════
# Thread-safe signal bridge
# ═══════════════════════════════════════════════════════════════════════════
class WorkerSignals(QObject):
    log = Signal(str, str)
    status = Signal(str)
    current = Signal(str)
    progress = Signal(int, int)          # value, maximum
    duration = Signal(str)
    finished = Signal(int, str)          # error_count, error_msg


# ═══════════════════════════════════════════════════════════════════════════
# Generate checkbox tick icon (temp SVG used by QSS)
# ═══════════════════════════════════════════════════════════════════════════
_tick_path = os.path.join(tempfile.gettempdir(), "raw_combiner_tick.svg")
with open(_tick_path, "w") as _f:
    _f.write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" '
        'stroke="white" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
_tick_url = _tick_path.replace("\\", "/")


# ═══════════════════════════════════════════════════════════════════════════
# QSS Stylesheet
# ═══════════════════════════════════════════════════════════════════════════
def load_stylesheet():
    with open(resource_path("app.qss"), "r", encoding="utf-8") as f:
        stylesheet = f.read()
    return (
        stylesheet
        .replace("__TICK_URL__", _tick_url)
        .replace("__FONT_TITLE__", UI_FONT_TITLE)
        .replace("__FONT_BODY__", UI_FONT_BODY)
        .replace("__FONT_MONO__", UI_FONT_MONO)
    )


STYLESHEET = load_stylesheet()


def get_app_stylesheet():
    return STYLESHEET


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

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._bg))
        painter.drawRoundedRect(rect, radius, radius)

        if self._animating:
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
            pen = QPen(QColor(self._border), 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

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


# ═══════════════════════════════════════════════════════════════════════════
# Main widget
# ═══════════════════════════════════════════════════════════════════════════
class CombinerWidget(QWidget):
    """RAW Files Combiner UI — embeddable as a QWidget (tab or standalone)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.theme_name = DEFAULT_THEME
        self.stop_requested = False
        self.processing_running = False
        self.start_time = None
        self._status_badge_state = None
        self._log_entries = []
        self._section_accent_bars = []
        self.site_checkboxes = {}  # site_name -> list of (QCheckBox, dir_path)
        self.site_paths = get_initial_site_paths()  # {site_name: base_dir}
        self.site_path_labels = {}  # {site_name: QLabel}

        self.signals = WorkerSignals()
        self.signals.log.connect(self._append_log)
        self.signals.status.connect(self._set_status)
        self.signals.current.connect(self._set_current)
        self.signals.progress.connect(self._set_progress)
        self.signals.duration.connect(self._set_duration)
        self.signals.finished.connect(self._on_finished)

        self._build_ui()
        self._set_processing_controls(False)

    # ── Build UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.setObjectName("central")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        body = QWidget()
        body.setObjectName("body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 6, 14, 6)
        body_layout.setSpacing(6)

        # ── BASE DIRECTORY card ────────────────────────────────────
        dir_card = self._make_section("BASE DIRECTORY", body_layout)
        dir_inner = dir_card.layout()

        for site_name in SITE_GROUPS:
            row = QHBoxLayout()
            row.setSpacing(10)

            site_lbl = QLabel(f"{site_name}:")
            site_lbl.setProperty("class", "dim")
            site_lbl.setFixedWidth(110)
            row.addWidget(site_lbl)

            path_lbl = QLabel(self._compact_path(self.site_paths.get(site_name, "")))
            path_lbl.setProperty("class", "file-name")
            path_lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 700; color: {self._theme_colors()['file_name']}; font-family: {UI_FONT_TITLE};"
            )
            path_lbl.setToolTip(self.site_paths.get(site_name, "(not set)"))
            path_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row.addWidget(path_lbl, 1)
            self.site_path_labels[site_name] = path_lbl

            btn = QPushButton("\U0001F4C2 Browse Folder")
            btn.setProperty("class", "small-btn")
            btn.setMinimumWidth(146)
            btn.clicked.connect(
                lambda checked=False, s=site_name: self._browse_site_dir(s)
            )
            row.addWidget(btn)

            dir_inner.addLayout(row)

        # ── LOGGER SELECTION card ──────────────────────────────────
        sel_card = self._make_section("LOGGER SELECTION", body_layout)
        sel_inner = sel_card.layout()
        sel_inner.setSpacing(5)

        # Summary + Select All / Clear All
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.selected_label = QLabel("0 / 0 selected")
        self.selected_label.setStyleSheet(self._pill_qss(*self._theme_colors()["selected_idle"]))
        top_row.addWidget(self.selected_label)
        top_row.addStretch()

        btn_sel = QPushButton("Select All")
        btn_sel.setProperty("class", "small-btn")
        btn_sel.clicked.connect(lambda: self._set_all_sites(True))
        top_row.addWidget(btn_sel)

        btn_clr = QPushButton("Clear All")
        btn_clr.setProperty("class", "small-btn")
        btn_clr.clicked.connect(lambda: self._set_all_sites(False))
        top_row.addWidget(btn_clr)
        sel_inner.addLayout(top_row)

        # Tabs per site
        self.tabs = QTabWidget()
        self.tabs.setObjectName("pipe-tabs")
        self._rebuild_site_tabs()

        self.tabs.currentChanged.connect(self._update_selection_summary)
        sel_inner.addWidget(self.tabs)
        self._update_selection_summary()

        # ── Action buttons ────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()

        self.btn_start = QPushButton("▶ Start Processing")
        self.btn_start.setObjectName("btn-start")
        self.btn_start.setToolTip("Start combining the selected directories.")
        self.btn_start.clicked.connect(self._start_processing)
        action_row.addWidget(self.btn_start)

        self.btn_abort = QPushButton("■ Abort")
        self.btn_abort.setObjectName("btn-abort")
        self.btn_abort.setToolTip("Abort is enabled only while processing is running.")
        self.btn_abort.clicked.connect(self._abort_processing)
        action_row.addWidget(self.btn_abort)

        sel_inner.addLayout(action_row)

        # ── PROCESSING STATUS card ────────────────────────────────────
        prog_card = self._make_section("PROCESSING STATUS", body_layout)
        prog_inner = prog_card.layout()
        prog_inner.setContentsMargins(14, 6, 14, 6)
        prog_inner.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        colors = self._theme_colors()
        self.status_badge = NeonBadge()
        sr = colors["status_ready"]
        self.status_badge.setNeonStyle(sr[0], sr[1], sr[2])
        status_row.addWidget(self.status_badge)
        self.status_label = QLabel("Ready to process selected directories.")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {colors['status_text']}; font-family: {UI_FONT_BODY};"
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
        self.progress_bar.setFormat("%v / %m directories")
        self.progress_bar.setFixedHeight(22)
        prog_row.addWidget(self.progress_bar, 1)
        self.current_item_label = QLabel("No active task")
        self.current_item_label.setProperty("class", "current-item")
        self.current_item_label.setStyleSheet(
            f"font-size: 11px; font-style: italic; color: {colors['current_item']}; font-family: {UI_FONT_TITLE};"
        )
        prog_row.addWidget(self.current_item_label)
        prog_inner.addLayout(prog_row)

        # ── PROCESSING LOG ────────────────────────────────────────────
        log_header = QHBoxLayout()
        accent_bar = QLabel()
        accent_bar.setFixedSize(4, 14)
        accent_bar.setProperty("class", "section-accent")
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

    # ── Theme ────────────────────────────────────────────────────────────
    def _theme_colors(self):
        return THEME_COLORS.get(self.theme_name, THEME_COLORS[DEFAULT_THEME])

    def apply_theme(self, theme_name):
        """Apply a theme (called by parent combined app when extractor toggles)."""
        self.theme_name = theme_name if theme_name in THEME_COLORS else DEFAULT_THEME
        colors = self._theme_colors()

        # Path labels
        for lbl in self.site_path_labels.values():
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 700; color: {colors['file_name']}; font-family: {UI_FONT_TITLE};"
            )

        # Status label
        if hasattr(self, "status_label"):
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {colors['status_text']}; font-family: {UI_FONT_BODY};"
            )

        # Current item label
        if hasattr(self, "current_item_label"):
            self.current_item_label.setStyleSheet(
                f"font-size: 11px; font-style: italic; color: {colors['current_item']}; font-family: {UI_FONT_TITLE};"
            )

        # Section accent bars
        for accent_bar in self._section_accent_bars:
            accent_bar.setStyleSheet(
                f"background-color: {colors['section_accent']}; border-radius: 2px;"
            )

        # Buttons
        self._apply_button_styles()

        # Selection summary
        if hasattr(self, "selected_label"):
            self._update_selection_summary()

        # Status badge
        if self._status_badge_state:
            self._set_status_badge(*self._status_badge_state)
        elif hasattr(self, "status_badge"):
            self._set_status_badge("READY", *colors["status_ready"])

        # Re-color log entries
        if hasattr(self, "log_text") and self._log_entries:
            self._recolor_log()

    # ── UI helpers ───────────────────────────────────────────────────────
    def _pill_qss(self, fg, bg, border):
        return (
            f"color: {fg}; font-size: 11px; font-weight: 700; font-family: {UI_FONT_BODY}; "
            f"background-color: {bg}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 2px 8px;"
        )

    def _button_qss(self, normal_bg, hover_bg, pressed_bg, border_color,
                    hover_border, pressed_border, font_size, padding,
                    disabled_bg="#243646", disabled_border="#31465a",
                    disabled_text="#6f8598"):
        return f"""
            QPushButton {{
                background-color: {normal_bg}; color: #ffffff;
                border: 1px solid {border_color}; border-radius: 8px;
                padding: {padding}; font-size: {font_size}px;
                font-weight: 700; font-family: {UI_FONT_BODY};
            }}
            QPushButton:hover {{
                background-color: {hover_bg}; border: 1px solid {hover_border};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg}; border: 1px solid {pressed_border};
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg}; color: {disabled_text};
                border: 1px solid {disabled_border};
            }}
        """

    def _apply_button_styles(self):
        colors = self._theme_colors()
        self.btn_start.setStyleSheet(self._button_qss(
            "#00a86b", "#00cc82", "#007a4d",
            "#33cc88", "#55eea0", "#00a86b",
            12, "7px 28px",
            colors["start_disabled_bg"], colors["start_disabled_border"], colors["start_disabled_text"],
        ))
        self.btn_abort.setStyleSheet(self._button_qss(
            "#d43535", "#ee4c4c", "#a82222",
            "#ee6666", "#ff8888", "#d43535",
            11, "7px 20px",
            colors["abort_disabled_bg"], colors["abort_disabled_border"], colors["abort_disabled_text"],
        ))

    def _make_section(self, title, parent_layout):
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

        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(6)
        parent_layout.addWidget(card)
        return card

    def _set_processing_controls(self, running):
        self.btn_abort.setEnabled(running)
        self.btn_start.setEnabled(not running)
        self.tabs.setEnabled(not running)
        for cbs in self.site_checkboxes.values():
            for cb, _ in cbs:
                cb.setEnabled(not running)
        if running:
            self.progress_bar.startWave()
        else:
            self.progress_bar.stopWave()

    def _set_status_badge(self, text, bg, border, fg="#dff7ff"):
        self._status_badge_state = (text, bg, border, fg)
        self.status_badge.setText(text)
        animate = text in ("RUNNING", "STOPPING")
        self.status_badge.setNeonStyle(fg, bg, border, animate=animate)

    # ── Path helpers ─────────────────────────────────────────────────────
    def _compact_path(self, path, max_len=52):
        if not path:
            return "(not set)"
        path = os.path.normpath(path)
        if len(path) <= max_len:
            return path
        parts = path.split(os.sep)
        if len(parts) <= 2:
            return path[:max_len - 3] + "..."
        return os.sep.join([parts[0], "...", parts[-2], parts[-1]])

    def _browse_site_dir(self, site_name):
        current = self.site_paths.get(site_name, "")
        start_dir = current if current and os.path.isdir(current) else ""
        chosen = QFileDialog.getExistingDirectory(
            self, f"Select base directory for {site_name}", start_dir
        )
        if not chosen:
            return
        self.site_paths[site_name] = chosen
        save_site_paths(self.site_paths)

        # Update path label
        lbl = self.site_path_labels[site_name]
        lbl.setText(self._compact_path(chosen))
        lbl.setToolTip(chosen)

        # Rebuild checkboxes with new paths
        self._rebuild_site_tabs()

    def _rebuild_site_tabs(self):
        """Rebuild all tab pages with current site_paths."""
        # Remember checked state
        prev_checked = {}
        for site_name, cbs in self.site_checkboxes.items():
            for cb, _ in cbs:
                prev_checked[(site_name, cb.text())] = cb.isChecked()

        # Clear tabs
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        self.site_checkboxes.clear()

        directories = build_directories(self.site_paths)

        for site_name, info in SITE_GROUPS.items():
            entries = directories.get(site_name, [])

            page = QWidget()
            page.setProperty("class", "tab-page")
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(10, 10, 10, 10)
            page_layout.setSpacing(8)

            # Select / Clear buttons per tab
            btn_row = QHBoxLayout()
            sa = QPushButton("Select Tab")
            sa.setProperty("class", "small-btn")
            sa.clicked.connect(
                lambda checked=False, s=site_name: self._set_all(
                    self.site_checkboxes[s], True
                )
            )
            btn_row.addWidget(sa)
            da = QPushButton("Clear Tab")
            da.setProperty("class", "small-btn")
            da.clicked.connect(
                lambda checked=False, s=site_name: self._set_all(
                    self.site_checkboxes[s], False
                )
            )
            btn_row.addWidget(da)
            btn_row.addStretch()
            page_layout.addLayout(btn_row)

            # Checkboxes grid
            grid = QGridLayout()
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(10)
            grid.setContentsMargins(0, 2, 0, 0)

            group_cbs = []
            cols = 5
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            for i, (label, dir_path) in enumerate(entries):
                cb = QCheckBox(label)
                cb.stateChanged.connect(self._update_selection_summary)
                if prev_checked.get((site_name, label), False):
                    cb.setChecked(True)
                grid.addWidget(cb, i // cols, i % cols)
                group_cbs.append((cb, dir_path))

            self.site_checkboxes[site_name] = group_cbs
            page_layout.addLayout(grid)
            page_layout.addStretch()

            self.tabs.addTab(page, site_name)

        self.tabs.blockSignals(False)
        self._update_selection_summary()

    # ── Checkbox helpers ─────────────────────────────────────────────────
    def _set_all(self, checkboxes, checked):
        for cb, _ in checkboxes:
            cb.setChecked(checked)
        self._update_selection_summary()

    def _set_all_sites(self, checked):
        for cbs in self.site_checkboxes.values():
            for cb, _ in cbs:
                cb.setChecked(checked)
        self._update_selection_summary()

    def _update_selection_summary(self, _=None):
        total = sum(len(cbs) for cbs in self.site_checkboxes.values())
        checked = sum(
            1 for cbs in self.site_checkboxes.values()
            for cb, _ in cbs if cb.isChecked()
        )
        self.selected_label.setText(f"{checked} / {total} selected")

        # Update tab labels with counts
        site_names = list(SITE_GROUPS.keys())
        for i, site_name in enumerate(site_names):
            cbs = self.site_checkboxes.get(site_name, [])
            grp_checked = sum(1 for cb, _ in cbs if cb.isChecked())
            grp_total = len(cbs)
            self.tabs.setTabText(i, f"{site_name} ({grp_checked}/{grp_total})")

        # Color the badge based on selection state
        colors = self._theme_colors()
        if checked > 0:
            self.selected_label.setStyleSheet(self._pill_qss(*colors["selected_active"]))
        else:
            self.selected_label.setStyleSheet(self._pill_qss(*colors["selected_idle"]))

    def _get_selected_dirs(self):
        selected = []
        for site_name, cbs in self.site_checkboxes.items():
            for cb, dir_path in cbs:
                if cb.isChecked():
                    selected.append(dir_path)
        return selected

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

    def _set_progress(self, value, maximum):
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(
            f"{value} / {maximum} director{'ies' if maximum != 1 else 'y'}"
        )

    def _set_current(self, text):
        self.current_item_label.setText(text or "No active task")

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
            self.log(f"Done with {error_count} error(s).", "warn")
        else:
            self._set_status_badge("SUCCESS", "#143d2d", "#2a9f67", "#d9ffe8")
            self.status_label.setText("All selected directories processed successfully.")
            self.log("All done!", "ok")

    # ── Processing ───────────────────────────────────────────────────────
    def _start_processing(self):
        if self.processing_running:
            return

        selected = self._get_selected_dirs()
        if not selected:
            self.log("No directories selected.", "warn")
            return

        self.start_time = datetime.now()
        self.processing_running = True
        self.stop_requested = False
        self._set_processing_controls(True)
        self._set_status_badge("RUNNING", "#14384f", "#2d8ab3")
        self.current_item_label.setText("Preparing worker...")
        self.signals.progress.emit(0, len(selected))
        self.signals.status.emit("Starting processing...")
        self.clear_log()
        self.log(f"Processing {len(selected)} director{'ies' if len(selected) != 1 else 'y'}...", "info")

        Thread(target=self._run_processing, args=(selected,), daemon=True).start()

    def _abort_processing(self):
        if not self.processing_running:
            return
        self.stop_requested = True
        self._set_status_badge("STOPPING", "#4a3018", "#ab7a2f", "#ffe2b0")
        self.status_label.setText("Abort requested. Finishing current step...")
        self.log("Abort requested by user.", "warn")

    def _run_processing(self, directories):
        total = len(directories)
        errors = []

        self.signals.progress.emit(0, total)
        self.signals.status.emit("Starting processing...")

        for idx, dir_path in enumerate(directories, start=1):
            if self.stop_requested:
                self.signals.status.emit("Processing aborted.")
                self.log("Processing aborted.", "warn")
                break

            self.signals.duration.emit(
                format_duration((datetime.now() - self.start_time).total_seconds())
            )

            sitename = os.path.basename(dir_path)
            self.signals.current.emit(sitename)
            self.signals.status.emit(f"Processing {sitename}...")

            def log_fn(msg, color="white"):
                self.signals.log.emit(msg, color)

            try:
                success = process_directory(dir_path, log_fn=log_fn)
                if not success:
                    errors.append((sitename, "skipped or no files"))
            except Exception as e:
                self.signals.log.emit(f"[ERROR] {sitename}: {e}", "err")
                errors.append((sitename, str(e)))

            self.signals.progress.emit(idx, total)

        # Final duration
        self.signals.duration.emit(
            format_duration((datetime.now() - self.start_time).total_seconds())
        )

        err_msg = "\n".join(f"{s}: {e}" for s, e in errors)
        self.signals.finished.emit(len(errors), err_msg)
