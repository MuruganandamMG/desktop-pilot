from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from google.genai import types

from desktop_agent.approvals import ApprovalManager
from desktop_agent.contracts import CancelToken, Effect, ModelTurn, Result, TokenUsage, ToolCall
from desktop_agent.executor import Executor
from desktop_agent.model import ModelError
from desktop_agent.policy import Registry, ToolSpec, runtime_registry
from desktop_agent.runner import Runner
from desktop_agent.settings import Settings
from desktop_agent.store import Store


def turn(*calls, text="", attempts=1):
    parts = [types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=dict(c.arguments))) for c in calls]
    return ModelTurn(types.Content(role="model", parts=parts or [types.Part(text=text)]), tuple(calls), text, TokenUsage(100, 10), attempts)


class Model:
    def __init__(self, *items):
        self.items, self.requests = list(items), []

    def next_step(self, context, history, tools, model_id, **kwargs):
        self.requests.append((context, list(history), model_id, kwargs))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def system(tmp_path):
    with Store(tmp_path / "tasks.sqlite") as store:
        yield store


def runner(store, model, settings=Settings(), *, effect=Effect.READ, cloud_safe=True):
    effects = []

    def validate(args):
        if dict(args):
            raise ValueError("No arguments supported")

    registry = Registry({"runtime_status": ToolSpec(effect, validate, lambda a: (),
        lambda p, c: effects.append(p) or Result("verified", "Read-only runtime", {"observed_state": "read-only"}),
        lambda p, r: r, "No change", cloud_safe=cloud_safe)})
    executor = Executor(store, registry, ApprovalManager(store))
    return Runner(store, executor, model, settings), effects


def test_tool_loop_preserves_provider_call_ids_and_never_persists_prompt(system):
    model = Model(turn(ToolCall("call-1", "runtime_status", {})), turn(text="Read-only mode"))
    run, effects = runner(system, model)
    task = system.create_task("private command")
    result = run.run(task, "private command api_key=secret", CancelToken())
    assert result.status == "verified" and len(effects) == 1
    assert system.get_task(task)["state"] == "SUCCEEDED"
    second_history = model.requests[1][1]
    assert second_history[0].parts[0].function_call.id == "call-1"
    assert second_history[1].parts[0].function_response.id == "call-1"
    assert "secret" not in model.requests[0][0].text
    assert "private command" not in str(system.events(task))
    assert system.model_request_count() == 2


def test_all_write_proposals_pause_without_execution(system):
    model = Model(turn(ToolCall("write", "runtime_status", {})))
    run, effects = runner(system, model, effect=Effect.REMOVE)
    task = system.create_task("remove")
    assert run.run(task, "remove", CancelToken()).status == "partial"
    assert system.get_task(task)["state"] == "WAITING_APPROVAL"
    assert effects == []


def test_tool_data_is_not_sent_without_a_source_approval(system):
    model = Model(turn(ToolCall("read", "runtime_status", {})), turn(text="should not be requested"))
    run, effects = runner(system, model, cloud_safe=False)
    task = system.create_task("read")
    assert run.run(task, "read", CancelToken()).status == "partial"
    assert len(effects) == 1 and len(model.requests) == 1
    assert system.get_task(task)["state"] == "PAUSED"


def test_request_cap_includes_retries(system):
    model = Model(turn(ToolCall("read", "runtime_status", {}), attempts=2))
    run, _ = runner(system, model, Settings(max_model_calls=2))
    task = system.create_task("status")
    result = run.run(task, "status", CancelToken())
    assert result.status == "partial"
    assert len(model.requests) == 1
    assert model.requests[0][3]["request_allowance"] == 2


def test_oversized_batch_executes_nothing(system):
    model = Model(turn(ToolCall("a", "runtime_status", {}), ToolCall("b", "runtime_status", {})))
    run, effects = runner(system, model, Settings(max_tool_actions=1))
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "partial"
    assert not effects


def test_duplicate_call_id_cannot_repeat_an_action(system):
    model = Model(turn(ToolCall("same", "runtime_status", {})), turn(ToolCall("same", "runtime_status", {})))
    run, effects = runner(system, model)
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "partial"
    assert len(effects) == 1


def test_no_tool_is_replayed_after_model_timeout(system):
    model = Model(turn(ToolCall("first", "runtime_status", {})), ModelError("timeout", "Request timed out", attempts=1))
    run, effects = runner(system, model)
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "partial"
    assert len(effects) == 1
    assert len(model.requests) == 2
    assert run.run(task, "status", CancelToken()).status == "failed"
    assert len(effects) == 1


def test_cancel_before_model_request_sends_nothing(system):
    model = Model()
    run, _ = runner(system, model)
    task = system.create_task("status")
    cancel = CancelToken()
    cancel.cancel()
    assert run.run(task, "status", cancel).status == "cancelled"
    assert not model.requests


def test_runtime_registry_exposes_only_its_known_read_tool():
    registry = runtime_registry()
    assert [d["name"] for d in registry.declarations()] == ["runtime_status"]
    assert registry.tool("runtime_status").effect == Effect.READ


def test_budget_stops_before_next_request_and_records_estimate(system):
    settings = Settings(budget_usd="0.0001", rate_model_id="gemini-3.5-flash-lite", input_rate_usd="1", output_rate_usd="2", rate_date="2026-10-19")
    model = Model(turn(ToolCall("a", "runtime_status", {})))
    run, _ = runner(system, model, settings)
    task = system.create_task("status")
    result = run.run(task, "status", CancelToken())
    assert result.status == "partial" and len(model.requests) == 1
    usage = [e for e in system.events(task) if e.get("kind") == "model_usage"]
    assert Decimal(usage[0]["estimate_usd"]) == Decimal("0.00012")


def test_budget_without_matching_rates_sends_nothing(system):
    model = Model()
    run, _ = runner(system, model, Settings(budget_usd="1"))
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "partial"
    assert not model.requests


def test_configured_escalation_happens_once_before_any_tool(system):
    model = Model(ModelError("invalid_response", "Invalid response", attempts=1, usage=TokenUsage(1, 1)), turn(text="Answer"))
    run, effects = runner(system, model, Settings(stronger_model_id="chosen-flash-model"))
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "verified"
    assert [r[2] for r in model.requests] == ["gemini-3.5-flash-lite", "chosen-flash-model"]
    assert not effects


def test_no_escalation_for_auth_errors(system):
    model = Model(ModelError("auth", "Authentication failed", attempts=1))
    run, _ = runner(system, model, Settings(stronger_model_id="chosen-flash-model"))
    task = system.create_task("status")
    assert run.run(task, "status", CancelToken()).status == "partial"
    assert len(model.requests) == 1


def test_another_active_task_blocks_a_new_run(system):
    active = system.create_task("first")
    system.begin_run(active)
    model = Model()
    run, _ = runner(system, model)
    task = system.create_task("second")
    assert run.run(task, "second", CancelToken()).status == "failed"
    assert not model.requests
