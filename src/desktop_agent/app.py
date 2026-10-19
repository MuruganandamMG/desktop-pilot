"""Manual-launch lifecycle; no automatic cloud requests or startup registration."""

from pathlib import Path
import sys


def acquire_instance_lock(data_path: Path):
    from PySide6.QtCore import QLockFile
    data_path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_path / "runtime.lock"))
    return lock if lock.tryLock(0) else None


def run(store, data_path: Path) -> int:
    from PySide6.QtWidgets import QApplication
    from .settings import load_settings
    from .ui import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Desktop Pilot")
    app.setOrganizationName("DesktopPilot")
    lock = acquire_instance_lock(data_path)
    if lock is None:
        print("Desktop Pilot is already running for this data folder", file=sys.stderr)
        return 2
    store.interrupt_inflight()
    window = MainWindow(store, load_settings(data_path / "settings.json"))
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()
