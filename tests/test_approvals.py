from dataclasses import replace

import pytest

from desktop_agent.approvals import ApprovalManager
from desktop_agent.contracts import Action, CancelToken, Effect, Result, Target
from desktop_agent.executor import Executor
from desktop_agent.policy import Registry, ToolSpec
from desktop_agent.store import Store


@pytest.fixture
def system(tmp_path):
    store = Store(tmp_path / "journal.sqlite")
    task = store.create_task("test")
    fingerprint = ["old"]
    calls = []

    def validate(args):
        if dict(args) != {"path": "example.txt"}:
            raise ValueError("Invalid target")

    spec = ToolSpec(
        Effect.REMOVE, validate,
        lambda action: (Target("file-1", "example.txt", fingerprint[0]),),
        lambda proposal, cancel: calls.append(proposal) or Result("verified", "recycled", {}),
        lambda proposal, result: result,
        "Recycle Bin recovery may be available",
    )
    registry = Registry({"files.recycle": spec})
    clock = [100.0]
    approvals = ApprovalManager(store, clock=lambda: clock[0])
    executor = Executor(store, registry, approvals)
    action = Action("a", task, "files.recycle", {"path": "example.txt"})
    yield store, executor, approvals, action, calls, fingerprint, clock
    store.close()


def approve(approvals, proposal):
    request = approvals.request_approval(proposal)
    approvals.record_user_decision(request, True)
    return request


def test_remove_never_runs_without_explicit_approval(system):
    _, executor, approvals, action, calls, _, _ = system
    proposal = executor.prepare(action)
    for grant in (None, "forged", approvals.request_approval(proposal)):
        with pytest.raises(PermissionError):
            executor.execute(proposal, grant, CancelToken())
    assert calls == []


def test_approval_is_single_use_and_action_is_never_replayed(system):
    _, executor, approvals, action, calls, _, _ = system
    proposal = executor.prepare(action)
    grant = approve(approvals, proposal)
    assert executor.execute(proposal, grant, CancelToken()).status == "verified"
    with pytest.raises(PermissionError):
        executor.execute(proposal, grant, CancelToken())
    second_grant = approve(approvals, proposal)
    with pytest.raises(PermissionError):
        executor.execute(proposal, second_grant, CancelToken())
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["expired", "target", "digest", "task", "effect", "cancel", "rejected"])
def test_stale_or_tampered_proposals_never_execute(system, change):
    store, executor, approvals, action, calls, fingerprint, clock = system
    proposal = executor.prepare(action)
    grant = approve(approvals, proposal)
    cancel = CancelToken()
    if change == "expired":
        clock[0] += 300
    elif change == "target":
        fingerprint[0] = "replaced"
    elif change == "digest":
        proposal = replace(proposal, digest="forged")
    elif change == "task":
        other = store.create_task("other")
        proposal = executor.prepare(replace(action, task_id=other))
    elif change == "effect":
        proposal = replace(proposal, effect=Effect.READ)
    elif change == "cancel":
        cancel.cancel()
    elif change == "rejected":
        grant = approvals.request_approval(proposal)
        approvals.record_user_decision(grant, False)
    with pytest.raises(PermissionError):
        executor.execute(proposal, grant, cancel)
    assert calls == []


def test_approval_decision_cannot_be_changed(system):
    _, executor, approvals, action, _, _, _ = system
    grant = approve(approvals, executor.prepare(action))
    with pytest.raises(PermissionError):
        approvals.record_user_decision(grant, True)


@pytest.mark.parametrize("name", ["shell", "powershell", "ui.click", "browser.evaluate", "approvals.accept"])
def test_unknown_capabilities_fail_closed(system, name):
    _, executor, _, action, calls, _, _ = system
    with pytest.raises(PermissionError):
        executor.prepare(replace(action, tool=name))
    assert not calls


def test_pending_approvals_are_invalid_after_recovery(system):
    store, executor, approvals, action, calls, _, _ = system
    proposal = executor.prepare(action)
    grant = approve(approvals, proposal)
    store.interrupt_inflight()
    with pytest.raises(PermissionError):
        executor.execute(proposal, grant, CancelToken())
    assert not calls
