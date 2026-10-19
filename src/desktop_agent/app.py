"""Manual-launch application; no cloud connection or startup registration."""

from pathlib import Path
import sys


def run(store, data_path: Path) -> int:
    from PySide6.QtWidgets import QApplication
    from .settings import load_settings
    from .ui import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Desktop Pilot")
    app.setOrganizationName("DesktopPilot")
    store.interrupt_inflight()
    window = MainWindow(store, load_settings(data_path / "settings.json"))
    window.show()
    return app.exec()
