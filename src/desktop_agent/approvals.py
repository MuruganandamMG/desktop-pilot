"""Local approval state. Deliberately absent from the capability registry."""

import time
from uuid import uuid4

from .contracts import Proposal
from .store import Store


class ApprovalManager:
    def __init__(self, store: Store, clock=time.time):
        self.store, self.clock = store, clock

    def request_approval(self, proposal: Proposal) -> str:
        self.store.get_task(proposal.action.task_id)
        approval_id = uuid4().hex
        with self.store.db:
            self.store.db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,0)",
                                  (approval_id, proposal.action.task_id, proposal.digest, self.clock() + 300, "pending"))
        return approval_id

    def record_user_decision(self, request_id: str, accepted: bool) -> None:
        if type(accepted) is not bool:
            raise ValueError("Approval decision must be explicit")
        with self.store.db:
            cursor = self.store.db.execute("""UPDATE approvals SET decision=?
                WHERE id=? AND decision='pending' AND expires>? AND consumed=0""",
                ("accepted" if accepted else "rejected", request_id, self.clock()))
            if cursor.rowcount != 1:
                raise PermissionError("Approval is missing, expired, or already decided")

    def consume(self, approval_id: str | None, proposal: Proposal) -> None:
        with self.store.db:
            cursor = self.store.db.execute("""UPDATE approvals SET consumed=1
                WHERE id=? AND task_id=? AND digest=? AND expires>?
                AND decision='accepted' AND consumed=0""",
                (approval_id, proposal.action.task_id, proposal.digest, self.clock()))
            if cursor.rowcount != 1:
                raise PermissionError("Explicit, current, single-use approval is required")
