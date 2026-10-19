"""Observe this app's Windows hotkey/session messages without injecting input."""

import ctypes
from ctypes import wintypes
import os

from PySide6.QtCore import QAbstractNativeEventFilter


HOTKEY_ID = 0x4450


class WindowsEvents(QAbstractNativeEventFilter):
    def __init__(self, window_id, on_stop, on_lock, on_unlock, *, user32=None, wtsapi32=None):
        super().__init__()
        self.window_id = int(window_id)
        self.on_stop, self.on_lock, self.on_unlock = on_stop, on_lock, on_unlock
        self.hotkey_registered = self.session_registered = False
        if os.name == "nt":
            if user32 is None:
                user32 = ctypes.WinDLL("user32.dll", use_last_error=True, winmode=0x800)
                user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
                user32.RegisterHotKey.restype = wintypes.BOOL
                user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.UnregisterHotKey.restype = wintypes.BOOL
            if wtsapi32 is None:
                wtsapi32 = ctypes.WinDLL("wtsapi32.dll", use_last_error=True, winmode=0x800)
                wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
                wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL
                wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
                wtsapi32.WTSUnRegisterSessionNotification.restype = wintypes.BOOL
        self.user32, self.wtsapi32 = user32, wtsapi32

    def start(self) -> tuple[bool, bool]:
        if self.user32 is not None and not self.hotkey_registered:
            self.hotkey_registered = bool(self.user32.RegisterHotKey(self.window_id, HOTKEY_ID, 0x4003, 0x13))
        if self.wtsapi32 is not None and not self.session_registered:
            self.session_registered = bool(self.wtsapi32.WTSRegisterSessionNotification(self.window_id, 0))
        return self.hotkey_registered, self.session_registered

    def handle_message(self, window_id, message, wparam) -> bool:
        if window_id != self.window_id:
            return False
        if message == 0x312 and wparam == HOTKEY_ID and self.hotkey_registered:
            self.on_stop()
            return True
        if message == 0x2B1 and self.session_registered:
            if wparam in (2, 4, 6, 7):  # Disconnect, logoff, or lock: never continue unattended.
                self.on_lock()
                return True
            if wparam == 8:
                self.on_unlock()
                return True
        return False

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        event = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        return self.handle_message(int(event.hWnd or 0), event.message, event.wParam), 0

    def close(self):
        if self.hotkey_registered:
            self.user32.UnregisterHotKey(self.window_id, HOTKEY_ID)
            self.hotkey_registered = False
        if self.session_registered:
            self.wtsapi32.WTSUnRegisterSessionNotification(self.window_id)
            self.session_registered = False
