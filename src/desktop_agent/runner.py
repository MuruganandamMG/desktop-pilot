"""Bounded Gemini loop. Non-read proposals always stop for local review."""

import hashlib
import json
from decimal import Decimal

from google.genai import types

from .context import ContextBundle, redact
from .contracts import Action, CancelToken, Effect, Result, TaskState, TokenUsage, plain
from .model import ModelError
from .settings import Settings


def request_context(command: str, context: ContextBundle | None = None) -> ContextBundle:
    if type(command) is not str or not command.strip() or len(command) > 8000:
        raise ValueError("Enter a command of 1–8000 characters")
    extra = context or ContextBundle("", ())
    text = redact(f"User command:\n{command}\n\nSelected untrusted context:\n{extra.text}")
    if len(text) > 32000:
        raise ValueError("Selected context exceeds the request limit")
    return ContextBundle(text, extra.sources)


class Runner:
    def __init__(self, store, executor, model, settings: Settings, *, context=None):
        self.store, self.executor, self.model, self.settings = store, executor, model, settings
        self.context = context

    def _estimate(self, model_id, usage):
        if model_id != self.settings.rate_model_id or not self.settings.rate_date or usage.input_tokens is None or usage.output_tokens is None:
            return None
        return (Decimal(self.settings.input_rate_usd) * usage.input_tokens + Decimal(self.settings.output_rate_usd) * usage.output_tokens) / 1_000_000

    def run(self, task_id: str, command: str, cancel: CancelToken, *, probe=False) -> Result:
        try:
            context = request_context(command, self.context)
            self.store.begin_run(task_id)
        except (PermissionError, ValueError) as exc:
            return Result("failed", str(exc), {})
        history, requests, actions = [], 0, 0
        spent, unknown_cost = Decimal(0), False
        input_tokens, output_tokens, unknown_tokens = 0, 0, False
        model_id, escalated = self.settings.model_id, False
        cap = Decimal(self.settings.budget_usd) if self.settings.budget_usd else None

        def stop(message, *, state=TaskState.PAUSED, status="partial"):
            self.store.transition(task_id, state)
            return Result(status, message, {"model_requests": requests, "tool_actions": actions,
                "model_id": model_id,
                "input_tokens": None if unknown_tokens else input_tokens, "output_tokens": None if unknown_tokens else output_tokens,
                "estimate_usd": None if unknown_cost else str(spent) if self.settings.rate_date else None})

        def record(usage, attempts):
            nonlocal requests, spent, unknown_cost, input_tokens, output_tokens, unknown_tokens
            requests += attempts
            unknown_tokens = unknown_tokens or usage.input_tokens is None or usage.output_tokens is None or attempts > 1
            input_tokens += usage.input_tokens or 0
            output_tokens += usage.output_tokens or 0
            estimate = self._estimate(model_id, usage)
            if attempts > 1:
                estimate = None  # Failed attempts can have unreported billable usage.
            unknown_cost = unknown_cost or estimate is None
            if estimate is not None:
                spent += estimate
            self.store.append_event(task_id, {"kind": "model_usage", "model": model_id, "attempts": attempts,
                "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                "estimate_usd": str(estimate) if estimate is not None else None,
                "rate_date": self.settings.rate_date or None})

        while True:
            if cancel.cancelled:
                return stop("Task cancelled; completed receipts are retained", state=TaskState.CANCELLED, status="cancelled")
            if requests >= self.settings.max_model_calls:
                return stop("Model request limit reached; start a reviewed new task to continue")
            if cap is not None and (unknown_cost or spent >= cap or self._estimate(model_id, TokenUsage(0, 0)) is None):
                return stop("Per-task estimated budget reached or usage/rates unavailable; no new request sent")
            try:
                turn = self.model.next_step(context, history, self.executor.registry.declarations(), model_id,
                    request_allowance=min(1 if cap is not None else 3, self.settings.max_model_calls - requests), cancel=cancel, force_tool=probe)
            except ModelError as exc:
                record(exc.usage, exc.attempts)
                if cancel.cancelled or exc.kind == "cancelled":
                    return stop("Task cancelled; an in-flight cloud request may still be billed", state=TaskState.CANCELLED, status="cancelled")
                if exc.kind == "invalid_response" and self.settings.stronger_model_id and not escalated and actions == 0 and not probe:
                    model_id, escalated = self.settings.stronger_model_id, True
                    continue
                return stop(str(exc))
            record(turn.usage, turn.attempts)
            if cancel.cancelled:
                return stop("Task cancelled after model response; no subsequent action executed", state=TaskState.CANCELLED, status="cancelled")
            if not turn.calls:
                if probe:
                    return stop("Model probe did not return a structured function call", state=TaskState.FAILED, status="failed")
                self.store.transition(task_id, TaskState.EXECUTING)
                self.store.transition(task_id, TaskState.VERIFYING)
                self.store.transition(task_id, TaskState.SUCCEEDED)
                return Result("verified", "Gemini replied; model text is advice, not verification of computer changes", {
                    "answer": redact(turn.text), "model_requests": requests, "tool_actions": actions,
                    "model_id": model_id,
                    "input_tokens": None if unknown_tokens else input_tokens, "output_tokens": None if unknown_tokens else output_tokens,
                    "estimate_usd": None if unknown_cost else str(spent) if self.settings.rate_date else None,
                })
            if actions + len(turn.calls) > self.settings.max_tool_actions:
                return stop("Tool-action limit would be exceeded; batch was not executed")
            prepared = []
            try:
                for call in turn.calls:
                    identity = call.id or json.dumps([call.name, plain(call.arguments)], sort_keys=True)
                    action_id = hashlib.sha256(identity.encode()).hexdigest()
                    proposal = self.executor.prepare(Action(action_id, task_id, call.name, call.arguments))
                    prepared.append((call, proposal))
            except (ValueError, PermissionError):
                return stop("Tool proposal failed local validation; no action in this batch executed")
            if any(proposal.effect != Effect.READ for _, proposal in prepared):
                return stop("A write/removal proposal needs local review; no action in this batch executed", state=TaskState.WAITING_APPROVAL)
            history.append(turn.content)
            responses = []
            for call, proposal in prepared:
                if cancel.cancelled:
                    return stop("Task cancelled; no further tool executed", state=TaskState.CANCELLED, status="cancelled")
                self.store.transition(task_id, TaskState.EXECUTING)
                try:
                    result = self.executor.execute(proposal, None, cancel)
                except PermissionError:
                    return stop("Tool execution denied or already attempted; no automatic replay")
                actions += 1
                self.store.transition(task_id, TaskState.VERIFYING)
                if result.status != "verified":
                    return stop("Tool outcome is not verified; inspect retained receipts before continuing")
                if probe:
                    self.store.transition(task_id, TaskState.SUCCEEDED)
                    return Result("verified", "Configured model returned a structured call; local read-only tool verified", {
                        "function_calling": True, "model_requests": requests, "tool_actions": actions,
                        "model_id": model_id,
                        "input_tokens": None if unknown_tokens else input_tokens, "output_tokens": None if unknown_tokens else output_tokens,
                        "estimate_usd": None if unknown_cost else str(spent) if self.settings.rate_date else None,
                    })
                if not self.executor.registry.tool(call.name).cloud_safe:
                    return stop("Tool completed locally; its output needs source approval before cloud upload")
                observation = redact(json.dumps({"summary": result.summary, "evidence": plain(result.evidence)}, ensure_ascii=False))[:12000]
                responses.append(types.Part(function_response=types.FunctionResponse(
                    id=call.id, name=call.name, response={"status": "verified", "observation": observation})))
                self.store.transition(task_id, TaskState.PLANNING)
            history.append(types.Content(role="user", parts=responses))
