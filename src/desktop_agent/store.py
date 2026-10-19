"""Transactional local task journal; restarting never resumes work."""

import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .contracts import TaskState


_NEXT = {
    TaskState.QUEUED: {TaskState.PLANNING},
    TaskState.PLANNING: {TaskState.WAITING_APPROVAL, TaskState.EXECUTING, TaskState.PAUSED},
    TaskState.WAITING_APPROVAL: {TaskState.EXECUTING, TaskState.PAUSED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.PAUSED},
    TaskState.VERIFYING: {TaskState.PLANNING, TaskState.SUCCEEDED, TaskState.PAUSED},
    TaskState.PAUSED: {TaskState.PLANNING},
    TaskState.INTERRUPTED: {TaskState.PLANNING},
}


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("Unsupported journal schema; refusing to modify it")
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, command TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                    digest TEXT NOT NULL, expires REAL NOT NULL,
                    decision TEXT NOT NULL, consumed INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS actions (
                    task_id TEXT REFERENCES tasks(id), id TEXT NOT NULL,
                    digest TEXT NOT NULL, PRIMARY KEY(task_id,id));
                PRAGMA user_version=1;
            """)

    def create_task(self, command: str) -> str:
        if type(command) is not str or not command.strip() or len(command) > 8000:
            raise ValueError("Command must contain 1–8000 characters")
        task_id = uuid4().hex
        # Persist a task label, not the user's potentially sensitive raw prompt.
        with self.db:
            self.db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)",
                            (task_id, "User task", TaskState.QUEUED, time.time()))
        return task_id

    def get_task(self, task_id: str) -> dict:
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def begin_run(self, task_id: str) -> None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.get_task(task_id)["state"] != TaskState.QUEUED:
                raise PermissionError("Only a new task may start; interrupted work needs explicit review")
            active = self.db.execute("""SELECT 1 FROM tasks WHERE id<>?
                AND state IN ('PLANNING','WAITING_APPROVAL','EXECUTING','VERIFYING') LIMIT 1""", (task_id,)).fetchone()
            if active:
                raise PermissionError("Another task is active")
            self.db.execute("UPDATE tasks SET state='PLANNING' WHERE id=?", (task_id,))

    def model_request_count(self) -> int:
        return sum(event.get("attempts", 0) for row in self.db.execute("SELECT payload FROM events")
                   if (event := json.loads(row[0])).get("kind") == "model_usage")

    def list_tasks(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 100")]

    def transition(self, task_id: str, state: TaskState) -> None:
        state = TaskState(state)
        with self.db:
            current = TaskState(self.get_task(task_id)["state"])
            allowed = _NEXT.get(current, set())
            if current in _NEXT:
                allowed = allowed | {TaskState.CANCELLED, TaskState.FAILED}
            if state not in allowed:
                raise ValueError(f"Invalid task transition: {current} → {state}")
            self.db.execute("UPDATE tasks SET state=? WHERE id=?", (state, task_id))

    def append_event(self, task_id: str, event: dict) -> None:
        self.get_task(task_id)
        payload = json.dumps(event, allow_nan=False)
        if len(payload) > 32000:
            raise ValueError("Event exceeds journal limit")
        with self.db:
            self.db.execute("INSERT INTO events(task_id,payload) VALUES (?,?)", (task_id, payload))

    def events(self, task_id: str) -> list[dict]:
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT payload FROM events WHERE task_id=? ORDER BY id", (task_id,))]

    def interrupt_inflight(self) -> int:
        with self.db:
            self.db.execute("UPDATE approvals SET decision='rejected' WHERE consumed=0")
            return self.db.execute("""UPDATE tasks SET state='INTERRUPTED'
                WHERE state IN ('QUEUED','PLANNING','WAITING_APPROVAL','EXECUTING','VERIFYING')""").rowcount

    def claim_action(self, task_id: str, action_id: str, digest: str) -> None:
        try:
            with self.db:
                self.db.execute("INSERT INTO actions VALUES (?,?,?)", (task_id, action_id, digest))
        except sqlite3.IntegrityError as exc:
            raise PermissionError("Action already attempted or task missing; no automatic replay") from exc

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
