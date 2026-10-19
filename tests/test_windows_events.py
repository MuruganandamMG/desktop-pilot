from desktop_agent.windows_events import WindowsEvents, HOTKEY_ID


class UserAPI:
    def __init__(self, result=True):
        self.result, self.calls = result, []

    def RegisterHotKey(self, *args):
        self.calls.append(("register", args))
        return self.result

    def UnregisterHotKey(self, *args):
        self.calls.append(("unregister", args))
        return True


class SessionAPI:
    def __init__(self, result=True):
        self.result, self.calls = result, []

    def WTSRegisterSessionNotification(self, *args):
        self.calls.append(("register", args))
        return self.result

    def WTSUnRegisterSessionNotification(self, *args):
        self.calls.append(("unregister", args))
        return True


def test_owned_hotkey_and_session_notifications_dispatch_without_input_injection(qapp):
    calls = []
    user, session = UserAPI(), SessionAPI()
    events = WindowsEvents(123, lambda: calls.append("stop"), lambda: calls.append("lock"), lambda: calls.append("unlock"), user32=user, wtsapi32=session)
    assert events.start() == (True, True)
    assert user.calls[0][1] == (123, HOTKEY_ID, 0x4003, 0x13)
    assert session.calls[0][1] == (123, 0)
    assert not events.handle_message(999, 0x312, HOTKEY_ID)
    assert not events.handle_message(123, 0x312, HOTKEY_ID + 1)
    assert events.handle_message(123, 0x312, HOTKEY_ID)
    assert events.handle_message(123, 0x2B1, 7)
    assert events.handle_message(123, 0x2B1, 8)
    assert calls == ["stop", "lock", "unlock"]
    events.close()
    events.close()
    assert len(user.calls) == len(session.calls) == 2


def test_registration_failures_are_reported_and_unowned_events_ignored(qapp):
    calls = []
    user, session = UserAPI(False), SessionAPI(False)
    events = WindowsEvents(123, lambda: calls.append("stop"), lambda: calls.append("lock"), lambda: None, user32=user, wtsapi32=session)
    assert events.start() == (False, False)
    assert not events.handle_message(123, 0x312, HOTKEY_ID)
    assert not events.handle_message(123, 0x2B1, 7)
    events.close()
    assert not calls
    assert len(user.calls) == len(session.calls) == 1
