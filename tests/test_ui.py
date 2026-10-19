from PySide6.QtCore import Qt

from desktop_agent.contracts import Action, CancelToken, Effect, Proposal, Result, Target
from desktop_agent.store import Store
from desktop_agent.ui import MainWindow, ApprovalDialog
from desktop_agent.context import ContextBundle
from desktop_agent.settings import Settings


def test_blank_request_is_rejected_without_a_task(qtbot, tmp_path):
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        qtbot.mouseClick(window.ask, Qt.MouseButton.LeftButton)
        assert store.list_tasks() == []
        assert "Enter a command" in window.message.text()


def test_approval_defaults_to_cancel_and_lists_exact_targets(qtbot):
    action = Action("a", "t", "files.recycle", {"path": "example.txt"})
    proposal = Proposal(action, Effect.REMOVE, (Target("file", "C:/example.txt (12 bytes)", "fp"),), "digest", "Recycle Bin if supported")
    dialog = ApprovalDialog(proposal)
    qtbot.addWidget(dialog)
    dialog.show()
    assert "example.txt" in dialog.details.toPlainText()
    assert "12 bytes" in dialog.details.toPlainText()
    assert "Recycle Bin" in dialog.details.toPlainText()
    assert dialog.cancel_button.isDefault()
    assert not dialog.approve_button.isDefault()
    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == 0


def test_cloud_preview_defaults_to_cancel_and_redacts_task_content(qtbot):
    from desktop_agent.ui import CloudPreviewDialog
    from desktop_agent.runner import request_context
    dialog = CloudPreviewDialog(Settings(), request_context("api_key=secret"))
    qtbot.addWidget(dialog)
    assert "secret" not in dialog.details.toPlainText()
    assert "[REDACTED]" in dialog.details.toPlainText()
    assert "generativelanguage.googleapis.com" in dialog.details.toPlainText()
    assert dialog.cancel_button.isDefault()
    assert not dialog.send_button.isDefault()


def test_rejected_cloud_preview_creates_no_task(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("desktop_agent.ui.CloudPreviewDialog.exec", lambda self: 0)
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.command.setText("Ask a question")
        qtbot.mouseClick(window.ask, Qt.MouseButton.LeftButton)
        assert store.list_tasks() == []
        assert not window._cloud_active


def test_cloud_worker_uses_own_store_and_does_not_attach_memory_by_default(qtbot, tmp_path, monkeypatch):
    from desktop_agent.contracts import ModelTurn, TokenUsage
    from google.genai import types
    requests = []

    class FakeClient:
        def __init__(self, settings):
            pass

        def next_step(self, context, history, tools, model_id, **kwargs):
            requests.append(context.text)
            return ModelTurn(types.Content(role="model", parts=[types.Part(text="Hello")]), (), "Hello", TokenUsage(2, 1))

    monkeypatch.setattr("desktop_agent.model.GeminiClient", FakeClient)
    monkeypatch.setattr("desktop_agent.ui.CloudPreviewDialog.exec", lambda self: 1)
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.show_memory_results(ContextBundle("private unselected note", ("note",)))
        window.command.setText("Hello")
        qtbot.mouseClick(window.ask, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not window._cloud_active)
        assert store.list_tasks()[0]["state"] == "SUCCEEDED"
        assert requests and "private unselected note" not in requests[0]
        assert "Hello" in window.results.toPlainText()
        assert "advice" in window.results.toPlainText()


def test_pause_and_emergency_stop_block_requests_without_auto_resume(qtbot, tmp_path):
    from desktop_agent.contracts import CancelToken
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window._cloud_cancel = CancelToken()
        window.set_cloud_active(True)
        window.emergency_stop()
        assert window._cloud_cancel.paused
        assert window._paused
        window.cloud_finished(Result("partial", "Paused", {}))
        assert not window.ask.isEnabled()
        window.pause_tasks(False)
        assert window.ask.isEnabled()
        assert store.list_tasks() == []


def test_lock_invalidates_approvals_and_unlock_does_not_resume(qtbot, tmp_path):
    from desktop_agent.approvals import ApprovalManager
    with Store(tmp_path / "journal.sqlite") as store:
        task = store.create_task("remove")
        proposal = Proposal(Action("a", task, "files.recycle", {}), Effect.REMOVE, (), "digest", "unknown")
        manager = ApprovalManager(store)
        grant = manager.request_approval(proposal)
        manager.record_user_decision(grant, True)
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.session_locked()
        import pytest
        with pytest.raises(PermissionError):
            manager.consume(grant, proposal)
        window.session_unlocked()
        assert window._paused and not window.ask.isEnabled()
        assert not window._session_locked


def test_pause_while_cloud_preview_is_open_prevents_send(qtbot, tmp_path, monkeypatch):
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.command.setText("status")
        def paused_preview(dialog):
            window.pause_tasks(True)
            return 1
        monkeypatch.setattr("desktop_agent.ui.CloudPreviewDialog.exec", paused_preview)
        qtbot.mouseClick(window.ask, Qt.MouseButton.LeftButton)
        assert store.list_tasks() == []


def test_missing_session_guard_disables_cloud_but_hotkey_conflict_has_visible_fallback(qtbot, tmp_path):
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.set_native_status(False, True)
        assert window.ask.isEnabled()
        assert "unavailable" in window.native_status.text()
        window.set_native_status(False, False)
        assert not window.ask.isEnabled()


def test_tray_pause_action_uses_same_gate(qtbot, tmp_path):
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.tray_pause.trigger()
        assert window._paused and not window.ask.isEnabled()
        window.tray_pause.trigger()
        assert not window._paused and window.ask.isEnabled()

def test_resume_retries_failed_approval_reset(qtbot, tmp_path, monkeypatch):
    import sqlite3
    with Store(tmp_path / 'journal.sqlite') as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        original = store.invalidate_approvals
        def fail():
            raise sqlite3.OperationalError('unavailable')
        monkeypatch.setattr(store, 'invalidate_approvals', fail)
        window.pause_tasks(True)
        window.pause_tasks(False)
        assert window._paused and not window.ask.isEnabled()
        monkeypatch.setattr(store, 'invalidate_approvals', original)
        window.pause_tasks(False)
        assert not window._paused and window.ask.isEnabled()


def test_hidden_tray_exit_quits_event_loop(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop_agent.store import Store
from desktop_agent.ui import MainWindow
app = QApplication([])
with Store(__import__('pathlib').Path(sys.argv[1])) as store:
    window = MainWindow(store)
    window.show()
    window.hide()
    QTimer.singleShot(0, window.tray_menu.actions()[-1].trigger)
    QTimer.singleShot(2000, lambda: app.exit(42))
    sys.exit(app.exec())
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'exit.sqlite')],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
