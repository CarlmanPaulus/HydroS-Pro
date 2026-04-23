import sys

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtGui import QIcon

from .main_window import (
    APP_ID, CURRENT_VERSION, WINDOW_TITLE,
    CombinerWidget, get_app_stylesheet, resource_path,
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
    app.setStyleSheet(get_app_stylesheet())

    try:
        app.setWindowIcon(QIcon(resource_path("HydroS.ico")))
    except Exception:
        pass

    window = QMainWindow()
    window.setWindowTitle(f"HydroS — RAW Combiner v{CURRENT_VERSION}")
    window.setMinimumSize(620, 500)
    window.resize(700, 580)
    try:
        window.setWindowIcon(QIcon(resource_path("HydroS.ico")))
    except Exception:
        pass

    widget = CombinerWidget()
    window.setCentralWidget(widget)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
