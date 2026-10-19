import pytest

from desktop_agent.contracts import Action, CancelToken


def test_actions_reject_unknown_fields_and_types():
    data = dict(id="a", task_id="t", tool="memory.search", arguments={"query": "editor"})
    action = Action.parse(data)
    data["arguments"]["query"] = "changed"
    assert action.arguments["query"] == "editor"
    with pytest.raises(TypeError):
        action.arguments["query"] = "changed"
    for invalid in ({**data, "approved": True}, {**data, "tool": 3}, {**data, "arguments": []}):
        with pytest.raises(ValueError):
            Action.parse(invalid)


def test_cancel_is_explicit_and_thread_safe():
    token = CancelToken()
    assert not token.cancelled
    token.cancel()
    assert token.cancelled

