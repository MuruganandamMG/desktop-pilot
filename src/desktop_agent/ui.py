"""Small native preview: inspect memory, queue requests, and review approvals."""

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QMainWindow,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from .contracts import TaskState
from .memory import MemoryStore
from .settings import Settings


class _SearchSignals(QObject):
    finished = Signal(str)


class _Search(QRunnable):
    def __init__(self, vault, query):
        super().__init__()
        self.vault, self.query = vault, query
        self.signals = _SearchSignals()

    def run(self):
        try:
            results = MemoryStore(Path(self.vault), {"Project", "Preferences", "Workflows", "Decisions", "Task Summaries"}).search(self.query)
            text = "\n\n".join(f"{r.path}\nModified: {r.modified_at}\nProvenance (note claim): {r.provenance}\n{r.text}" for r in results)
            self.signals.finished.emit(text or "No matching granted notes.")
        except (ValueError, OSError) as exc:
            self.signals.finished.emit(f"Memory unavailable: {exc}")


class MainWindow(QMainWindow):
    def __init__(self, store, settings: Settings | None = None):
        super().__init__()
        self.store, self.settings = store, settings or Settings()
        self.setWindowTitle("Desktop Pilot — foundation preview")
        self.resize(760, 680)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel("Desktop Pilot")
        font = title.font()
        font.setPointSize(22)
        title.setFont(font)
        layout.addWidget(title)
        layout.addWidget(QLabel("Local foundation preview · No cloud calls or computer-control tools enabled"))
        self.command = QLineEdit()
        label = QLabel("&Request to save for later")
        label.setBuddy(self.command)
        layout.addWidget(label)
        self.command.setMaxLength(8000)
        self.command.setAccessibleName("Request to save for later")
        layout.addWidget(self.command)
        self.submit = QPushButton("Save request")
        self.submit.clicked.connect(self.submit_command)
        layout.addWidget(self.submit)
        self.message = QLabel("Saved requests stay paused until execution is implemented.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        layout.addWidget(QLabel("Recent task states · Raw requests are not retained"))
        self.history = QListWidget()
        self.history.setMaximumHeight(110)
        layout.addWidget(self.history)
        self.query = QLineEdit()
        query_label = QLabel("&Search local memory")
        query_label.setBuddy(self.query)
        layout.addWidget(query_label)
        layout.addWidget(self.query)
        self.search = QPushButton("Search granted project folders")
        self.search.setEnabled(bool(self.settings.vault_path))
        self.search.clicked.connect(self.search_memory)
        layout.addWidget(self.search)
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        self.results.setAccessibleName("Local memory results with source paths")
        self.results.setPlainText("No vault configured." if not self.settings.vault_path else "Notes stay local. Nothing is sent to Gemini in this preview.")
        layout.addWidget(self.results)
        self.setCentralWidget(body)
        self.refresh()

    def refresh(self):
        self.history.clear()
        for task in self.store.list_tasks():
            self.history.addItem(f"{task['id'][:8]} · {task['state']}")

    def submit_command(self):
        command = self.command.text().strip()
        if not command:
            self.message.setText("Enter a request first.")
            return
        try:
            task = self.store.create_task(command)
            self.store.transition(task, TaskState.PLANNING)
            self.store.transition(task, TaskState.PAUSED)
        except (ValueError, OSError) as exc:
            self.message.setText(f"Request could not be saved: {exc}")
            return
        self.command.clear()
        self.message.setText("Request state saved. Gemini planning is not enabled in this build; no action was taken. Re-enter the request when planning becomes available.")
        self.refresh()

    def search_memory(self):
        self.search.setEnabled(False)
        self.results.setPlainText("Searching local notes…")
        self._worker = _Search(self.settings.vault_path, self.query.text())
        self._worker.signals.finished.connect(self.show_memory_results)
        QThreadPool.globalInstance().start(self._worker)

    def show_memory_results(self, text):
        self.results.setPlainText(text)
        self.search.setEnabled(True)


class ApprovalDialog(QDialog):
    def __init__(self, proposal, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review exact operation")
        self.resize(560, 400)
        layout = QVBoxLayout(self)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(
            f"Operation: {proposal.action.tool}\nEffect: {proposal.effect}\n"
            f"Exact targets ({len(proposal.targets)}):\n"
            + "\n".join(target.display for target in proposal.targets)
            + f"\n\nRecovery: {proposal.recovery}\n\nApproval applies once and expires after five minutes."
        )
        layout.addWidget(self.details)
        buttons = QDialogButtonBox()
        self.approve_button = buttons.addButton("Approve listed operation", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.approve_button.setAutoDefault(False)
        self.approve_button.setDefault(False)
        self.cancel_button.setDefault(True)
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
