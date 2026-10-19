from PySide6.QtCore import Qt

from desktop_agent.contracts import Action, Effect, Proposal, Target
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
