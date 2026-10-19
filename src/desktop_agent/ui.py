"""Native preview: inspect memory and explicitly consent to cloud requests."""

from pathlib import Path
from dataclasses import replace
import sqlite3

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from .contracts import CancelToken, Result, TaskState
from .context import ContextBundle, Source, prepare_context, redact
from .memory import MemoryStore
from .settings import Settings


class _SearchSignals(QObject):
    finished = Signal(object)


class _Search(QRunnable):
    def __init__(self, vault, query):
        super().__init__()
        self.vault, self.query = vault, query
        self.signals = _SearchSignals()

    def run(self):
        try:
            results = MemoryStore(Path(self.vault), {"Project", "Preferences", "Workflows", "Decisions", "Task Summaries"}).search(self.query)
            sources = [Source(r.path, f"{r.path}\nModified: {r.modified_at}\nProvenance (note claim): {r.provenance}\n{r.text}") for r in results]
            bundle = prepare_context(sources, {source.id for source in sources})
            self.signals.finished.emit(bundle if sources else "No matching granted notes.")
        except (ValueError, OSError) as exc:
            self.signals.finished.emit(f"Memory unavailable: {exc}")


class _CloudRun(QRunnable):
    def __init__(self, database, task_id, command, settings, cancel, context, probe):
        super().__init__()
        self.database, self.task_id, self.command = database, task_id, command
        self.settings, self.cancel, self.context, self.probe = settings, cancel, context, probe
        self.signals = _SearchSignals()

    def run(self):
        from .approvals import ApprovalManager
        from .executor import Executor
        from .model import GeminiClient, ModelError
        from .policy import runtime_registry
        from .runner import Runner
        from .store import Store

        result = Result("failed", "Cloud task could not finish; no task was automatically retried", {})
        try:
            with Store(self.database) as store:
                try:
                    client = GeminiClient(self.settings)
                    executor = Executor(store, runtime_registry(), ApprovalManager(store))
                    result = Runner(store, executor, client, self.settings, context=self.context).run(self.task_id, self.command, self.cancel, probe=self.probe)
                except ModelError as exc:
                    store.transition(self.task_id, TaskState.FAILED)
                    result = Result("failed", str(exc), {})
                except Exception:
                    state = store.get_task(self.task_id)["state"]
                    if state in {"QUEUED", "PLANNING", "EXECUTING", "VERIFYING", "WAITING_APPROVAL"}:
                        store.transition(self.task_id, TaskState.FAILED)
        except Exception:
            pass  # Keep raw provider/credential exceptions out of UI and journals.
        self.signals.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, store, settings: Settings | None = None):
        super().__init__()
        self.store, self.settings = store, settings or Settings()
        self._cloud_active, self._close_requested = False, False
        self._memory_bundle = ContextBundle("", ())
        self.setWindowTitle("Desktop Pilot — read-only cloud preview")
        self.resize(800, 820)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel("Desktop Pilot")
        font = title.font()
        font.setPointSize(22)
        title.setFont(font)
        layout.addWidget(title)
        notice = QLabel("Gemini runs only after preview and consent. No desktop, browser, or removal tools enabled.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        model_row = QHBoxLayout()
        model_label = QLabel("&Gemini model")
        self.model_input = QLineEdit(self.settings.model_id)
        self.model_input.setMaxLength(128)
        model_label.setBuddy(self.model_input)
        model_row.addWidget(model_label)
        model_row.addWidget(self.model_input)
        self.key_button = QPushButton("Set API key locally")
        self.key_button.clicked.connect(self.configure_key)
        model_row.addWidget(self.key_button)
        layout.addLayout(model_row)
        self.command = QLineEdit()
        label = QLabel("&Request")
        label.setBuddy(self.command)
        layout.addWidget(label)
        self.command.setMaxLength(8000)
        self.command.setAccessibleName("Request to preview before sending to Gemini")
        layout.addWidget(self.command)
        cloud_row = QHBoxLayout()
        self.ask = QPushButton("Preview and ask Gemini")
        self.ask.clicked.connect(lambda: self.start_cloud(False))
        self.probe = QPushButton("Preview and test model")
        self.probe.clicked.connect(lambda: self.start_cloud(True))
        self.stop = QPushButton("Cancel cloud task")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel_cloud)
        for button in (self.ask, self.probe, self.stop):
            cloud_row.addWidget(button)
        layout.addLayout(cloud_row)
        self.message = QLabel("Type a request, then review the cloud preview. Add the API key locally before the first model test.")
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
        self.results.setPlainText("No vault configured." if not self.settings.vault_path else "Notes stay local unless you attach them and approve a cloud preview.")
        layout.addWidget(self.results)
        self.attach_memory = QCheckBox("Attach the last local search excerpts to this cloud request")
        self.attach_memory.setEnabled(False)
        layout.addWidget(self.attach_memory)
        self.setCentralWidget(body)
        self.refresh()

    def refresh(self):
        self.history.clear()
        for task in self.store.list_tasks():
            self.history.addItem(f"{task['id'][:8]} · {task['state']}")

    def search_memory(self):
        self._memory_bundle = ContextBundle("", ())
        self.attach_memory.setChecked(False)
        self.attach_memory.setEnabled(False)
        self.search.setEnabled(False)
        self.results.setPlainText("Searching local notes…")
        self._worker = _Search(self.settings.vault_path, self.query.text())
        self._worker.signals.finished.connect(self.show_memory_results)
        QThreadPool.globalInstance().start(self._worker)

    def show_memory_results(self, result):
        self._memory_bundle = result if isinstance(result, ContextBundle) else ContextBundle("", ())
        self.results.setPlainText(result.text if isinstance(result, ContextBundle) else str(result))
        self.attach_memory.setEnabled(bool(self._memory_bundle.text) and not self._cloud_active)
        self.search.setEnabled(True)

    def configure_key(self):
        from .settings import set_api_key
        key, accepted = QInputDialog.getText(self, "Store Gemini API key locally", "API key (stored in Windows Credential Manager)", QLineEdit.EchoMode.Password)
        if not accepted:
            return
        try:
            set_api_key(key)
        except Exception:
            self.message.setText("API key could not be saved. Check Windows Credential Manager; no cloud request was made.")
        else:
            self.message.setText("API key saved locally. Use the model test to check account access; no request has been made yet.")

    def start_cloud(self, probe):
        from .runner import request_context
        if self._cloud_active:
            return
        command = "Call runtime_status once with no arguments." if probe else self.command.text().strip()
        context = self._memory_bundle if self.attach_memory.isChecked() and not probe else None
        try:
            settings = replace(self.settings, model_id=self.model_input.text().strip())
            bundle = request_context(command, context)
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        if CloudPreviewDialog(settings, bundle, self).exec() != QDialog.DialogCode.Accepted:
            self.message.setText("Cloud preview cancelled; nothing sent.")
            return
        try:
            task = self.store.create_task(command)
        except (ValueError, sqlite3.Error):
            self.message.setText("Task could not be saved; no cloud request started.")
            return
        self._cloud_cancel = CancelToken()
        self._cloud_worker = _CloudRun(self.store.path, task, command, settings, self._cloud_cancel, context, probe)
        self._cloud_worker.signals.finished.connect(self.cloud_finished)
        self.set_cloud_active(True)
        self.message.setText("Contacting Gemini. You can cancel this task.")
        self.refresh()
        QThreadPool.globalInstance().start(self._cloud_worker)

    def set_cloud_active(self, active):
        self._cloud_active = active
        for control in (self.command, self.model_input, self.key_button, self.ask, self.probe):
            control.setEnabled(not active)
        self.stop.setEnabled(active)
        self.attach_memory.setEnabled(not active and bool(self._memory_bundle.text))

    def cancel_cloud(self):
        if self._cloud_active:
            self._cloud_cancel.cancel()
            self.message.setText("Cancelling; an in-flight request may still be billed. No subsequent tool will start.")

    def cloud_finished(self, result):
        self.set_cloud_active(False)
        self.message.setText(result.summary)
        answer = result.evidence.get("answer", "")
        estimate = result.evidence.get("estimate_usd")
        self.results.setPlainText(
            f"Gemini reply (unverified advice)\nModel: {result.evidence.get('model_id', 'not contacted')}\nRequests: {result.evidence.get('model_requests', 0)} · Tool calls: {result.evidence.get('tool_actions', 0)}\n"
            f"Returned tokens — input: {result.evidence.get('input_tokens', 'unavailable')}, output: {result.evidence.get('output_tokens', 'unavailable')}\n"
            f"Estimated USD: {estimate if estimate is not None else 'unavailable; provider billing may differ'}\n\n{answer or result.summary}"
        )
        self.refresh()
        if self._close_requested:
            self.close()

    def closeEvent(self, event):
        if self._cloud_active:
            self._close_requested = True
            self.cancel_cloud()
            event.ignore()
        else:
            event.accept()


class CloudPreviewDialog(QDialog):
    def __init__(self, settings, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review cloud request")
        self.resize(650, 540)
        layout = QVBoxLayout(self)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(
            "Destination: https://generativelanguage.googleapis.com\n"
            f"Model: {settings.model_id}\nConfigured escalation model: {settings.stronger_model_id or 'none'}\n"
            f"Limits: {settings.max_model_calls} actual API attempts, {settings.max_tool_actions} tool actions, {settings.max_output_tokens} output tokens per response.\n"
            f"Per-task estimated USD cap: {settings.budget_usd or 'not set'} (not a provider hard cap).\n"
            "Only the constant read-only runtime_status tool is enabled. No file, browser, or desktop content is collected automatically.\n"
            f"Selected sources: {', '.join(context.sources) or 'typed command only'}\n\nTask content sent:\n{redact(context.text)}"
        )
        layout.addWidget(self.details)
        buttons = QDialogButtonBox()
        self.send_button = buttons.addButton("Send this task to Gemini", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.send_button.setAutoDefault(False)
        self.send_button.setDefault(False)
        self.cancel_button.setDefault(True)
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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
