from PySide6.QtCore import Qt

from desktop_agent.contracts import Action, Effect, Proposal, Target
from desktop_agent.store import Store
from desktop_agent.ui import MainWindow, ApprovalDialog


def test_request_is_saved_paused_without_executing(qtbot, tmp_path):
    with Store(tmp_path / "journal.sqlite") as store:
        window = MainWindow(store)
        qtbot.addWidget(window)
        window.command.setText("Open my editor")
        qtbot.mouseClick(window.submit, Qt.MouseButton.LeftButton)
        assert store.list_tasks()[0]["state"] == "PAUSED"
        assert "not enabled" in window.message.text()
        assert "Open my editor" not in str(store.list_tasks())


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
