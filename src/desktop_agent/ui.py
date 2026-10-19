"""Native preview: inspect memory and explicitly consent to cloud requests."""

from pathlib import Path
from dataclasses import replace
import sqlite3

from PySide6.QtCore import QObject, QRunnable, QSignalBlocker, QThreadPool, Signal, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMenu, QPushButton, QStyle, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
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
        self._paused = self._session_locked = False
        self._session_guard_available = True
        self._approval_journal_ok = True
        self._exit_requested = False
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
        safety_row = QHBoxLayout()
        self.pause_button = QPushButton("Pause tasks")
        self.pause_button.setCheckable(True)
        self.pause_button.toggled.connect(self.pause_tasks)
        self.hide_button = QPushButton("Hide to tray")
        self.hide_button.setEnabled(False)
        self.hide_button.clicked.connect(self.hide)
        safety_row.addWidget(self.pause_button)
        safety_row.addWidget(self.hide_button)
        layout.addLayout(safety_row)
        self.native_status = QLabel("Native safety controls initialize when the Windows app launches.")
        self.native_status.setWordWrap(True)
        layout.addWidget(self.native_status)
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
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("Show", self.show_from_tray)
        self.tray_pause = QAction("Pause tasks", self)
        self.tray_pause.setCheckable(True)
        self.tray_pause.toggled.connect(self.pause_tasks)
        self.tray_menu.addAction(self.tray_pause)
        self.tray_menu.addAction("Cancel active task", self.cancel_cloud)
        self.tray_menu.addAction("Exit", self.request_exit)
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
            self.message.setText("API key saved locally. Process GEMINI_API_KEY and the project .env take precedence when set. Use the model test to check access; no request made yet.")

    def start_cloud(self, probe):
        from .runner import request_context
        if self._cloud_active or self._paused or self._session_locked or not self._session_guard_available:
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
        if self._paused or self._session_locked or not self._session_guard_available:
            self.message.setText("Task paused during preview; nothing sent.")
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
        for control in (self.command, self.model_input, self.key_button):
            control.setEnabled(not active)
        for control in (self.ask, self.probe):
            control.setEnabled(not active and not self._paused and not self._session_locked and self._session_guard_available)
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
        if self._paused:
            self.message.setText("Paused. Completed receipts retained; resume permits new reviewed tasks only.")
        if self._close_requested:
            self.close()

    def pause_tasks(self, paused):
        if not paused and not self._approval_journal_ok:
            try:
                self.store.invalidate_approvals()
            except sqlite3.Error:
                paused = True
            else:
                self._approval_journal_ok = True
        if not paused and (self._session_locked or not self._session_guard_available):
            paused = True
        self._paused = bool(paused)
        for control in (self.pause_button, self.tray_pause):
            with QSignalBlocker(control):
                control.setChecked(self._paused)
                control.setText("Resume new tasks" if self._paused else "Pause tasks")
        if self._paused:
            if self._cloud_active:
                self._cloud_cancel.pause()
            for dialog in self.findChildren(QDialog):
                dialog.reject()
            try:
                self.store.invalidate_approvals()
            except sqlite3.Error:
                self._approval_journal_ok = False
                self.message.setText("Paused; approval journal unavailable. Do not resume until it is accessible.")
            else:
                self._approval_journal_ok = True
                self.message.setText("Paused; pending approvals invalidated. Existing tasks will not resume automatically.")
        else:
            self.message.setText("Ready for a new reviewed task. Previous tasks remain paused.")
        self.set_cloud_active(self._cloud_active)

    def emergency_stop(self):
        self.pause_tasks(True)
        self.message.setText("Emergency stop: tasks paused. Review receipts before starting a new task.")

    def session_locked(self):
        self._session_locked = True
        self.pause_tasks(True)

    def session_unlocked(self):
        self._session_locked = False
        self.set_cloud_active(self._cloud_active)
        self.message.setText("Session unlocked; tasks remain paused until you explicitly resume new tasks.")

    def set_native_status(self, hotkey, session):
        self._session_guard_available = bool(session)
        shortcut = "Ctrl+Alt+Pause ready" if hotkey else "Ctrl+Alt+Pause unavailable; use visible Pause/Cancel"
        self.native_status.setText(f"{shortcut}. " + ("Session lock monitoring ready." if session else "Session lock monitoring unavailable; cloud tasks disabled."))
        if not session:
            self.pause_tasks(True)
        self.set_cloud_active(self._cloud_active)

    def install_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        self.tray.setToolTip("Desktop Pilot")
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda reason: self.show_from_tray() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.hide_button.setEnabled(True)
        return True

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def request_exit(self):
        self._exit_requested = True
        self.close()

    def closeEvent(self, event):
        if self._cloud_active:
            self._close_requested = True
            self.cancel_cloud()
            event.ignore()
        else:
            if hasattr(self, "tray"):
                self.tray.hide()
            event.accept()
            if self._exit_requested:
                QApplication.instance().quit()


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
