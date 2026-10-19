import pytest

from desktop_agent.contracts import TaskState
from desktop_agent.store import Store


def test_task_transitions_and_recovery_preserve_evidence(tmp_path):
    path = tmp_path / "tasks.sqlite"
    with Store(path) as store:
        task = store.create_task("open project")
        with pytest.raises(ValueError):
            store.transition(task, TaskState.SUCCEEDED)
        store.transition(task, TaskState.PLANNING)
        store.append_event(task, {"summary": "selected editor"})
    with Store(path) as store:
        assert store.interrupt_inflight() == 1
        assert store.get_task(task)["state"] == "INTERRUPTED"
        assert store.events(task) == [{"summary": "selected editor"}]
        assert store.interrupt_inflight() == 0


def test_paused_and_terminal_tasks_do_not_resume(tmp_path):
    with Store(tmp_path / "tasks.sqlite") as store:
        task = store.create_task("inspect")
        store.transition(task, TaskState.CANCELLED)
        assert store.interrupt_inflight() == 0
        with pytest.raises(ValueError):
            store.transition(task, TaskState.PLANNING)


def test_unknown_task_is_not_silently_accepted(tmp_path):
    with Store(tmp_path / "tasks.sqlite") as store:
        with pytest.raises(KeyError):
            store.transition("missing", TaskState.PLANNING)
