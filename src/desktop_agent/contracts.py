"""Strict, immutable data exchanged across the model/tool boundary."""

from dataclasses import dataclass
from enum import StrEnum
import json
from threading import Event, Lock
from types import MappingProxyType
from collections.abc import Mapping


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


class TaskState(StrEnum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class Effect(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    REMOVE = "REMOVE"
    EXTERNAL_SEND = "EXTERNAL_SEND"
    PRIVILEGED = "PRIVILEGED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class Action:
    id: str
    task_id: str
    tool: str
    arguments: Mapping

    def __post_init__(self):
        for value in (self.id, self.task_id, self.tool):
            if type(value) is not str or not value.strip() or len(value) > 128:
                raise ValueError("Action identifiers must be nonempty strings of at most 128 characters")
        if not isinstance(self.arguments, Mapping) or any(type(key) is not str for key in self.arguments):
            raise ValueError("Action arguments must be a JSON object")
        try:
            encoded = json.dumps(plain(self.arguments), allow_nan=False)
            if len(encoded.encode("utf-8")) > 32768:
                raise ValueError("Action arguments exceed 32 KiB")
            copied = json.loads(encoded)
        except (TypeError, RecursionError) as exc:
            raise ValueError("Action arguments must contain bounded JSON values") from exc
        object.__setattr__(self, "arguments", freeze(copied))

    @classmethod
    def parse(cls, data: dict):
        if type(data) is not dict or set(data) != {"id", "task_id", "tool", "arguments"}:
            raise ValueError("Unexpected action fields")
        return cls(**data)


@dataclass(frozen=True)
class Target:
    identity: str
    display: str
    fingerprint: str


@dataclass(frozen=True)
class Proposal:
    action: Action
    effect: Effect
    targets: tuple[Target, ...]
    digest: str
    recovery: str


@dataclass(frozen=True)
class Result:
    status: str
    summary: str
    evidence: Mapping


class CancelToken:
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._reason = None

    @property
    def cancelled(self):
        return self._event.is_set()

    def cancel(self):
        self._signal("cancelled")

    @property
    def paused(self):
        return self._reason == "paused"

    def pause(self):
        self._signal("paused")

    def _signal(self, reason):
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str | None
    name: str
    arguments: Mapping


@dataclass(frozen=True)
class ModelTurn:
    content: object
    calls: tuple[ToolCall, ...]
    text: str
    usage: TokenUsage
    attempts: int = 1


@dataclass(frozen=True)
class CapabilityReport:
    model_id: str
    available: bool
    function_calling: bool
    usage: TokenUsage
