"""HydroS - combined launcher for Manual Extractor + RAW Files Combiner."""

import os
import shutil
import sys
import webbrowser
from threading import Thread

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from manual_extractor.main_window import (
    INITIAL_THEME,
    THEME_COLORS,
    THEME_ICON_DARK,
    THEME_ICON_LIGHT,
    UI_FONT_BODY,
    UI_FONT_TITLE,
    ExtractorWidget,
    get_app_stylesheet,
    normalize_theme_name,
    resource_path,
)
from manual_extractor.updater import (
    RELEASE_URL,
    cleanup_update_downloads,
    compare_versions,
    download_file,
    extract_patch_zip,
    fetch_latest_release,
    fetch_latest_release_asset,
    fetch_remote_version,
    get_update_download_dir,
    get_install_dir,
    is_major_update,
    make_unique_path,
    select_installer_asset,
    select_zip_asset,
    write_patch_script,
)
from RAW_combiner.main_window import CombinerWidget

APP_TITLE = "HydroS Pro"
APP_VERSION = "3.0.7"


class _UiCallbackEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback):
        super().__init__(self.EVENT_TYPE)
        self.callback = callback


def set_windows_app_id():
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hydros.app")
    except Exception:
        pass


def set_windows_taskbar_icon(window, ico_path):
    """Force both small and big window icons via Win32 API."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        hwnd = int(window.winId())

        hicon_big = user32.LoadImageW(0, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)

        hicon_small = user32.LoadImageW(0, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    except Exception:
        pass


def _app_icon():
    if getattr(sys, "frozen", False):
        icon = QIcon(sys.executable)
        if not icon.isNull():
            return icon

    candidates = [
        os.path.join(os.path.dirname(sys.executable), "HydroS.ico"),
        resource_path("HydroS.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_extractor", "HydroS.ico"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


class HydroSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.theme_name = normalize_theme_name(INITIAL_THEME)
        self.update_check_running = False
        self.update_download_running = False
        self.update_progress_dialog = None

        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(760, 800)
        self.resize(800, 880)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("main-tabs")
        self.setCentralWidget(self.tabs)

        self.extractor = ExtractorWidget(enable_updates=False)
        self.tabs.addTab(self.extractor, "Extract GWL")

        self.combiner = CombinerWidget()
        self.tabs.addTab(self.combiner, "Combine RAW")

        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 6, 0)
        corner_layout.setSpacing(8)

        self.btn_update = QPushButton("Check Updates")
        self.btn_update.setObjectName("btn-update")
        self.btn_update.setToolTip(f"Check for HydroS updates. Current version: {APP_VERSION}")
        self.btn_update.clicked.connect(lambda: self._check_for_updates(manual=True))
        corner_layout.addWidget(self.btn_update)

        self.btn_theme = QPushButton("")
        self.btn_theme.setObjectName("btn-theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        corner_layout.addWidget(self.btn_theme)

        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        self.extractor.btn_theme_toggle = self.btn_theme

        original_apply = self.extractor._apply_theme

        def synced_apply_theme(theme_name, save=True):
            self.theme_name = normalize_theme_name(theme_name)
            original_apply(self.theme_name, save=save)
            self.combiner.apply_theme(self.theme_name)
            self._apply_toolbar_styles()

        self.extractor._apply_theme = synced_apply_theme

        self.combiner.apply_theme(self.theme_name)
        self._apply_toolbar_styles()

        self.statusBar().showMessage(f"{APP_TITLE} v{APP_VERSION} ready")
        cleanup_update_downloads()
        self._check_for_updates(manual=False)

    def event(self, event):
        if event.type() == _UiCallbackEvent.EVENT_TYPE:
            event.callback()
            return True
        return super().event(event)

    def _post_to_ui(self, callback):
        app = QApplication.instance()
        if app is not None:
            app.postEvent(self, _UiCallbackEvent(callback))

    def _toggle_theme(self):
        self.extractor._toggle_theme()

    def _theme_colors(self):
        return THEME_COLORS[self.theme_name]

    def _toolbar_button_qss(self, accent=False):
        is_dark = self.theme_name == "dark"
        if accent:
            border = "#2daee3" if is_dark else "#4d96b8"
            fg = "#dff7ff" if is_dark else "#173246"
            bg = "#14384f" if is_dark else "#dfeff8"
            hover = "#1b4864" if is_dark else "#cfe6f2"
        else:
            border = "#ffffff" if is_dark else "#000000"
            fg = "#ffffff" if is_dark else "#000000"
            bg = "transparent"
            hover = "transparent"

        return f"""
            QPushButton {{
                color: {fg};
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 700;
                font-family: {UI_FONT_BODY};
            }}
            QPushButton:hover {{
                border-color: {'#45dcf8' if is_dark else '#0088aa'};
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {bg};
            }}
            QPushButton:disabled {{
                color: {'#6f8598' if is_dark else '#6a7f8d'};
                border-color: {'#31475a' if is_dark else '#bccbd7'};
                background-color: {'#243746' if is_dark else '#edf4f9'};
            }}
        """

    def _apply_toolbar_styles(self):
        self.btn_theme.setText(THEME_ICON_LIGHT if self.theme_name == "dark" else THEME_ICON_DARK)
        self.btn_theme.setStyleSheet(self._toolbar_button_qss(accent=False))
        self.btn_update.setStyleSheet(self._toolbar_button_qss(accent=True))
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.setStyleSheet(self._dialog_stylesheet("#00b4d8"))

    def _dialog_stylesheet(self, accent):
        colors = self._theme_colors()
        return f"""
            QDialog, QProgressDialog {{
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
            QLabel#msg-body, QLabel {{
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
            QProgressBar {{
                border: 1px solid {colors['dialog_border']};
                border-radius: 6px;
                text-align: center;
                background-color: {colors['dialog_bg']};
                color: {colors['dialog_text']};
                min-height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 5px;
            }}
        """

    def _show_msg(self, title, message, level="info"):
        accent_map = {"info": "#00b4d8", "warning": "#ffb347", "error": "#ff5252"}
        icon_map = {"info": "\u2139", "warning": "\u26A0", "error": "\u2716"}
        accent = accent_map.get(level, "#00b4d8")

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(self._dialog_stylesheet(accent))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon_map.get(level, "\u2139"))
        icon_lbl.setObjectName("msg-icon")
        top.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("msg-title")
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        body_lbl = QLabel(message)
        body_lbl.setObjectName("msg-body")
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        dlg.exec()

    def _show_update_dialog(self, latest_version, major):
        dlg = QDialog(self)
        dlg.setWindowTitle("Update Available")
        dlg.setMinimumWidth(430)
        dlg.setStyleSheet(self._dialog_stylesheet("#00b4d8"))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("HydroS Update Ready")
        title_lbl.setObjectName("msg-title")
        layout.addWidget(title_lbl)

        if major:
            body = (
                f"Major update {latest_version} is available.\n"
                f"Current version: {APP_VERSION}\n\n"
                "This update uses the installer."
            )
            action_label = "Download Installer"
        else:
            body = (
                f"Patch update {latest_version} is available.\n"
                f"Current version: {APP_VERSION}\n\n"
                "This update will download the patch package and restart HydroS to apply it."
            )
            action_label = "Update Now"

        msg = QLabel(body)
        msg.setObjectName("msg-body")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        download_btn = QPushButton(action_label)
        browser_btn = QPushButton("Open Releases")
        later_btn = QPushButton("Later")

        result = {"value": "later"}

        def choose_download():
            result["value"] = "download"
            dlg.accept()

        def choose_browser():
            result["value"] = "browser"
            dlg.accept()

        download_btn.clicked.connect(choose_download)
        browser_btn.clicked.connect(choose_browser)
        later_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(download_btn)
        btn_row.addWidget(browser_btn)
        btn_row.addWidget(later_btn)
        layout.addLayout(btn_row)

        dlg.exec()
        return result["value"]

    def _show_launch_installer_dialog(self, installer_path, latest_version):
        dlg = QDialog(self)
        dlg.setWindowTitle("Installer Ready")
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet(self._dialog_stylesheet("#00b4d8"))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("Installer Downloaded")
        title_lbl.setObjectName("msg-title")
        layout.addWidget(title_lbl)

        msg = QLabel(
            f"HydroS {latest_version} has been downloaded.\n\n"
            "Launch the installer now?\n\n"
            f"{installer_path}"
        )
        msg.setObjectName("msg-body")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        launch_btn = QPushButton("Launch Installer")
        later_btn = QPushButton("Later")

        result = {"value": False}

        def choose_launch():
            result["value"] = True
            dlg.accept()

        launch_btn.clicked.connect(choose_launch)
        later_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(launch_btn)
        btn_row.addWidget(later_btn)
        layout.addLayout(btn_row)

        dlg.exec()
        return result["value"]

    def _set_update_button_state(self):
        self.btn_update.setEnabled(not self.update_check_running and not self.update_download_running)

    def _check_for_updates(self, manual=False):
        if self.update_download_running:
            if manual:
                self._show_msg("Update In Progress", "An installer download is already in progress.", "warning")
            return

        if self.update_check_running:
            if manual:
                self._show_msg("Checking for Updates", "HydroS is already checking for updates.", "warning")
            return

        self.update_check_running = True
        self._set_update_button_state()
        self.statusBar().showMessage("Checking for updates...")
        Thread(target=self._check_for_updates_worker, args=(manual,), daemon=True).start()

    def _check_for_updates_worker(self, manual):
        try:
            latest_version = fetch_remote_version()
        except Exception as exc:
            error_message = str(exc)

            def _show_error():
                self.update_check_running = False
                self._set_update_button_state()
                self.statusBar().showMessage("Update check failed.")
                if manual:
                    self._show_msg(
                        "Update Check Failed",
                        f"HydroS could not check for updates.\n\n{error_message}",
                        "error",
                    )

            self._post_to_ui(_show_error)
            return

        def _finish_check():
            self.update_check_running = False
            self._set_update_button_state()

            if compare_versions(APP_VERSION, latest_version) < 0:
                self.statusBar().showMessage(f"Update available: v{latest_version}")
                major = is_major_update(APP_VERSION, latest_version)
                action = self._show_update_dialog(latest_version, major)
                if action == "download":
                    self._start_update_download(latest_version, major)
                elif action == "browser":
                    webbrowser.open(RELEASE_URL)
                return

            if manual:
                self.statusBar().showMessage(f"{APP_TITLE} v{APP_VERSION} is up to date")
                self._show_msg(
                    "No Update Available",
                    f"You are already using the latest version.\n\nCurrent version: {APP_VERSION}",
                    "info",
                )
            else:
                self.statusBar().showMessage(f"{APP_TITLE} v{APP_VERSION} ready")

        self._post_to_ui(_finish_check)

    def _start_update_download(self, latest_version, major):
        if self.update_download_running:
            self._show_msg("Update In Progress", "An installer download is already in progress.", "warning")
            return

        self.update_download_running = True
        self._set_update_button_state()
        initial_label = (
            f"Preparing installer for v{latest_version}..."
            if major
            else f"Preparing patch update v{latest_version}..."
        )
        self.statusBar().showMessage(initial_label)

        self.update_progress_dialog = QProgressDialog(initial_label, "", 0, 100, self)
        self.update_progress_dialog.setWindowTitle("HydroS Update")
        self.update_progress_dialog.setCancelButton(None)
        self.update_progress_dialog.setWindowModality(Qt.WindowModal)
        self.update_progress_dialog.setMinimumDuration(0)
        self.update_progress_dialog.setAutoClose(False)
        self.update_progress_dialog.setValue(0)
        self.update_progress_dialog.setStyleSheet(self._dialog_stylesheet("#00b4d8"))
        self.update_progress_dialog.show()

        target = self._download_major_update if major else self._download_patch_update
        Thread(target=target, args=(latest_version,), daemon=True).start()

    def _set_update_status(self, text):
        self.statusBar().showMessage(text)
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.setLabelText(text)

    def _set_update_progress(self, value, maximum):
        if self.update_progress_dialog is None:
            return
        self.update_progress_dialog.setMaximum(maximum)
        self.update_progress_dialog.setValue(value)

    def _close_update_progress_dialog(self):
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.close()
            self.update_progress_dialog = None

    def _download_patch_update(self, latest_version):
        destination = None
        try:
            release_info = fetch_latest_release(latest_version)
            asset = select_zip_asset(release_info["assets"])
            if not asset:
                asset = select_installer_asset(release_info["assets"])
                if asset:
                    self._download_major_update(latest_version)
                    return
                raise RuntimeError("No .zip patch asset or installer asset was found in the latest GitHub release.")

            download_dir = get_update_download_dir()
            cleanup_update_downloads()
            os.makedirs(download_dir, exist_ok=True)
            destination = make_unique_path(os.path.join(download_dir, asset.get("name") or "update.zip"))

            download_file(
                asset["browser_download_url"],
                destination,
                lambda text: self._post_to_ui(lambda text=text: self._set_update_status(text)),
                lambda value, maximum: self._post_to_ui(
                    lambda value=value, maximum=maximum: self._set_update_progress(value, maximum)
                ),
            )

            extract_dir = os.path.join(download_dir, "_extracted")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)
            source_dir = extract_patch_zip(destination, extract_dir)
            install_dir = get_install_dir()
            script_path = write_patch_script(source_dir, install_dir)

            def _apply_patch():
                self.update_download_running = False
                self._set_update_button_state()
                self._close_update_progress_dialog()
                self.statusBar().showMessage(f"Applying patch update v{latest_version}...")
                try:
                    self._show_msg(
                        "Applying Update",
                        f"Patch update {latest_version} is ready.\n\nHydroS will restart now to apply it.",
                        "info",
                    )
                    import subprocess

                    subprocess.Popen(
                        ["cmd", "/c", script_path],
                        creationflags=0x00000008,
                    )
                    QApplication.instance().quit()
                except Exception as exc:
                    self._show_msg(
                        "Patch Launch Failed",
                        "The patch files were downloaded, but HydroS could not restart to apply them.\n\n"
                        f"{exc}\n\nTemporary update files are in:\n{download_dir}",
                        "error",
                    )

            self._post_to_ui(_apply_patch)

        except Exception as exc:
            error_message = str(exc)
            if destination and os.path.exists(destination):
                try:
                    os.remove(destination)
                except OSError:
                    pass

            def _show_error():
                self.update_download_running = False
                self._set_update_button_state()
                self._close_update_progress_dialog()
                self.statusBar().showMessage("Patch update failed. Opening releases page...")
                self._show_msg(
                    "Patch Update Failed",
                    "Automatic patch update could not be completed.\n\n"
                    f"{error_message}\n\n"
                    "The GitHub releases page will open so you can download the update manually.",
                    "error",
                )
                webbrowser.open(RELEASE_URL)

            self._post_to_ui(_show_error)

    def _download_major_update(self, latest_version):
        destination = None
        try:
            release_info = fetch_latest_release_asset(latest_version)
            download_dir = get_update_download_dir()
            cleanup_update_downloads()
            os.makedirs(download_dir, exist_ok=True)
            destination = make_unique_path(os.path.join(download_dir, release_info["asset_name"]))

            download_file(
                release_info["asset_url"],
                destination,
                lambda text: self._post_to_ui(lambda text=text: self._set_update_status(text)),
                lambda value, maximum: self._post_to_ui(
                    lambda value=value, maximum=maximum: self._set_update_progress(value, maximum)
                ),
            )

            def _show_success():
                self.update_download_running = False
                self._set_update_button_state()
                self._close_update_progress_dialog()
                self.statusBar().showMessage(f"Installer ready: {os.path.basename(destination)}")
                if self._show_launch_installer_dialog(destination, latest_version):
                    try:
                        os.startfile(destination)
                        QApplication.instance().quit()
                    except Exception as exc:
                        self._show_msg(
                            "Launch Failed",
                            "The installer was downloaded, but could not be launched automatically.\n\n"
                            f"{exc}\n\nPlease run it manually from:\n{destination}",
                            "error",
                        )

            self._post_to_ui(_show_success)

        except Exception as exc:
            error_message = str(exc)
            if destination and os.path.exists(destination):
                try:
                    os.remove(destination)
                except OSError:
                    pass

            def _show_error():
                self.update_download_running = False
                self._set_update_button_state()
                self._close_update_progress_dialog()
                self.statusBar().showMessage("Update download failed. Opening releases page...")
                self._show_msg(
                    "Installer Download Failed",
                    "Automatic installer download could not be completed.\n\n"
                    f"{error_message}\n\n"
                    "The GitHub releases page will open so you can download the installer manually.",
                    "error",
                )
                webbrowser.open(RELEASE_URL)

            self._post_to_ui(_show_error)


def main():
    set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(get_app_stylesheet(INITIAL_THEME))
    app.setWindowIcon(_app_icon())

    window = HydroSWindow()
    window.show()

    ico_path = resource_path("HydroS.ico")
    if not os.path.isfile(ico_path):
        ico_path = os.path.join(os.path.dirname(sys.executable), "HydroS.ico")
    if os.path.isfile(ico_path):
        set_windows_taskbar_icon(window, ico_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
