"""The only dispatch boundary; never repeats a claimed action."""

from threading import Lock

from .approvals import ApprovalManager
from .contracts import CancelToken, Effect, Proposal, Result
from .policy import Registry
from .store import Store


class Executor:
    def __init__(self, store: Store, registry: Registry, approvals: ApprovalManager):
        self.store, self.registry, self.approvals = store, registry, approvals
        self._lock = Lock()

    def prepare(self, action):
        self.store.get_task(action.task_id)
        return self.registry.prepare(action)

    def execute(self, proposal: Proposal, approval_id: str | None, cancel: CancelToken) -> Result:
        if not self._lock.acquire(blocking=False):
            raise PermissionError("Another action is active")
        try:
            if cancel.cancelled:
                raise PermissionError("Task was cancelled")
            state = self.store.get_task(proposal.action.task_id)["state"]
            if state in ("INTERRUPTED", "CANCELLED", "SUCCEEDED", "FAILED", "PAUSED"):
                raise PermissionError("Task is not active")
            current = self.registry.prepare(proposal.action)
            if current != proposal:
                raise PermissionError("Proposal or target changed; obtain a fresh preview")
            if current.effect != Effect.READ:
                self.approvals.consume(approval_id, current)
            if cancel.cancelled:
                raise PermissionError("Task was cancelled")
            self.store.claim_action(current.action.task_id, current.action.id, current.digest)
            spec = self.registry.tool(current.action.tool)
            try:
                result = spec.execute(current, cancel)
                verified = spec.verify(current, result)
            except Exception:
                # The side effect may have completed: retaining the claim prevents replay.
                verified = Result("unknown", "Action interrupted; inspect its effects before continuing", {})
            self.store.append_event(current.action.task_id, {
                "action_id": current.action.id, "digest": current.digest, "status": verified.status,
            })
            return verified
        finally:
            self._lock.release()
