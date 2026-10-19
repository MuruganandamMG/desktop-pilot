"""Explicit capability registry. Unknown capabilities are never executable."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json

from .contracts import Action, CancelToken, Effect, Proposal, Result, Target, plain


@dataclass(frozen=True)
class ToolSpec:
    effect: Effect
    validate: Callable[[Mapping], None]
    snapshot: Callable[[Action], tuple[Target, ...]]
    execute: Callable[[Proposal, CancelToken], Result]
    verify: Callable[[Proposal, Result], Result]
    recovery: str
    cloud_safe: bool = False
    description: str = "Registered local capability"
    parameters_json_schema: dict | None = None


class Registry:
    def __init__(self, tools: dict[str, ToolSpec]):
        self._tools = dict(tools)

    def tool(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise PermissionError(f"Unsupported capability: {name}") from exc

    def declarations(self) -> list[dict]:
        return [{"name": name, "description": spec.description,
                 "parameters_json_schema": spec.parameters_json_schema or {
                     "type": "object", "properties": {}, "additionalProperties": False,
                 }} for name, spec in self._tools.items()
                if spec.effect not in (Effect.PRIVILEGED, Effect.UNSUPPORTED)]

    def prepare(self, action: Action) -> Proposal:
        spec = self.tool(action.tool)
        if spec.effect in (Effect.PRIVILEGED, Effect.UNSUPPORTED):
            raise PermissionError("This capability requires manual intervention")
        spec.validate(action.arguments)
        targets = tuple(spec.snapshot(action))
        payload = {
            "id": action.id, "task": action.task_id, "tool": action.tool,
            "arguments": plain(action.arguments), "effect": spec.effect.value,
            "targets": [(t.identity, t.display, t.fingerprint) for t in targets],
            "recovery": spec.recovery,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        return Proposal(action, spec.effect, targets, digest, spec.recovery)


def runtime_registry() -> Registry:
    def validate(arguments):
        if arguments:
            raise ValueError("runtime_status accepts no arguments")

    def status(proposal, cancel):
        return Result("verified", "Read-only cloud preview; no computer-control tools enabled", {"observed_state": "read-only"})

    return Registry({"runtime_status": ToolSpec(
        Effect.READ, validate, lambda action: (), status, lambda proposal, result: result,
        "No system change", cloud_safe=True, description="Read the assistant's supported runtime mode; does not inspect the computer",
    )})
