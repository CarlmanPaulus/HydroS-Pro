import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PySide6.QtGui import QIcon

from .main_window import (
    APP_ID, CURRENT_VERSION, INITIAL_THEME,
    CombinerWidget, ExtractorWidget, get_app_stylesheet, resource_path,
)


def set_windows_app_id():
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def main():
    set_windows_app_id()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(get_app_stylesheet(INITIAL_THEME))

    try:
        app.setWindowIcon(QIcon(resource_path("HydroS.ico")))
    except Exception:
        pass

    window = QMainWindow()
    window.setWindowTitle(f"HydroS v{CURRENT_VERSION}")
    window.setMinimumSize(700, 780)
    window.resize(940, 860)
    try:
        window.setWindowIcon(QIcon(resource_path("HydroS.ico")))
    except Exception:
        pass

    app_tabs = QTabWidget()
    app_tabs.setObjectName("app-tabs")
    app_tabs.addTab(CombinerWidget(), "RAW Combiner")
    app_tabs.addTab(ExtractorWidget(), "MWT Extractor")
    app_tabs.setCurrentIndex(1)
    window.setCentralWidget(app_tabs)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
