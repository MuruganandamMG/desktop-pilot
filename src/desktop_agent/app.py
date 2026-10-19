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
    events = None
    try:
        from .windows_events import WindowsEvents
        try:
            events = WindowsEvents(int(window.winId()), window.emergency_stop, window.session_locked, window.session_unlocked)
            app.installNativeEventFilter(events)
            window.set_native_status(*events.start())
        except OSError:
            window.set_native_status(False, False)
        window.install_tray()
        return app.exec()
    finally:
        try:
            if hasattr(window, "tray"):
                window.tray.hide()
            if events is not None:
                app.removeNativeEventFilter(events)
                events.close()
        finally:
            lock.unlock()
