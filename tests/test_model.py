import asyncio
from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import types

from desktop_agent.context import ContextBundle
from desktop_agent.model import GeminiClient, ModelError
from desktop_agent.settings import Settings


TOOLS = [{"name": "runtime_status", "description": "Read the assistant mode", "parameters_json_schema": {"type": "object", "properties": {}, "additionalProperties": False}}]


def response(parts=None, **kwargs):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts or [types.Part(text="Ready")]), finish_reason="STOP")],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=8, candidates_token_count=3, thoughts_token_count=2),
        **kwargs,
    )


class FakeAPI:
    def __init__(self, *items):
        self.items, self.requests, self.options = list(items), [], []

    def factory(self, **options):
        self.options.append(options)
        return SimpleNamespace(aio=self)

    async def __aenter__(self):
        return SimpleNamespace(models=SimpleNamespace(generate_content=self.generate))

    async def __aexit__(self, *_):
        pass

    async def generate(self, **request):
        self.requests.append(request)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_manual_calls_preserve_opaque_content_and_usage():
    content = response([types.Part(function_call=types.FunctionCall(id="call-1", name="runtime_status", args={}), thought_signature=b"opaque-signature")])
    api = FakeAPI(content)
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory)
    turn = client.next_step(ContextBundle("api_key=secret", ()), [], TOOLS, "gemini-3.5-flash-lite")
    assert turn.content is content.candidates[0].content
    assert turn.calls[0].id == "call-1"
    assert turn.calls[0].name == "runtime_status"
    assert turn.usage.input_tokens == 8
    assert turn.usage.output_tokens == 5
    request = api.requests[0]
    assert request["config"].automatic_function_calling.disable is True
    assert request["config"].max_output_tokens == 1024
    assert "secret" not in request["contents"][0].parts[0].text
    assert api.options[0]["http_options"].retry_options.attempts == 1
    assert api.options[0]["vertexai"] is False


@pytest.mark.parametrize("code,kind", [(401,"auth"), (403,"auth"), (429,"quota"), (404,"model_unavailable"), (400,"invalid_request")])
def test_terminal_api_errors_are_safe_and_never_retried(code, kind):
    api = FakeAPI(genai.errors.APIError(code, {"error": {"message": "do not leak test-key"}}))
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory)
    with pytest.raises(ModelError) as caught:
        client.next_step(ContextBundle("hello", ()), [], TOOLS, "gemini-3.5-flash-lite")
    assert caught.value.kind == kind
    assert "test-key" not in str(caught.value)
    assert len(api.requests) == 1


def test_transient_model_request_retries_do_not_execute_tools():
    api = FakeAPI(httpx.ConnectError("network"), response())
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory, retry_delay=0)
    turn = client.next_step(ContextBundle("hello", ()), [], [], "gemini-3.5-flash-lite", request_allowance=2)
    assert turn.attempts == 2
    assert len(api.requests) == 2


def test_allowance_caps_actual_requests():
    api = FakeAPI(httpx.ConnectError("private message"), response())
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory, retry_delay=0)
    with pytest.raises(ModelError) as caught:
        client.next_step(ContextBundle("hello", ()), [], [], "gemini-3.5-flash-lite", request_allowance=1)
    assert caught.value.kind == "network"
    assert caught.value.attempts == 1
    assert len(api.requests) == 1


@pytest.mark.parametrize("parts", [
    [types.Part(function_call=types.FunctionCall(name="shell", args={"command": "remove"}))],
    [types.Part(function_call=types.FunctionCall(name="runtime_status", args={}), text="ambiguous")],
])
def test_unadvertised_or_ambiguous_parts_are_rejected(parts):
    api = FakeAPI(response(parts))
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory)
    with pytest.raises(ModelError) as caught:
        client.next_step(ContextBundle("hello", ()), [], TOOLS, "gemini-3.5-flash-lite")
    assert caught.value.kind == "invalid_response"
    assert caught.value.usage.input_tokens == 8


def test_probe_requires_a_valid_structured_call():
    api = FakeAPI(response([types.Part(function_call=types.FunctionCall(name="runtime_status", args={}))]))
    client = GeminiClient(Settings(), api_key="test-key", client_factory=api.factory)
    report = client.probe_model("gemini-3.5-flash-lite")
    assert report.available and report.function_calling
    assert api.requests[0]["config"].tool_config.function_calling_config.mode == "ANY"


def test_real_sdk_transport_is_offline_and_serializes_schema():
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1}})

    def factory(**kwargs):
        kwargs["http_options"].httpx_async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        return genai.Client(**kwargs)

    client = GeminiClient(Settings(), api_key="test-key", client_factory=factory)
    assert client.next_step(ContextBundle("hello", ()), [], TOOLS, "gemini-3.5-flash-lite").text == "Hello"
    assert len(requests) == 1
    assert requests[0].url.host == "generativelanguage.googleapis.com"


def test_missing_key_does_not_create_a_client(monkeypatch):
    monkeypatch.setattr("desktop_agent.model.get_api_key", lambda: None)
    with pytest.raises(ModelError, match="API key"):
        GeminiClient(Settings())


def test_request_deadline_cancels_slow_transport():
    class SlowAPI(FakeAPI):
        async def generate(self, **request):
            await asyncio.sleep(2)
            return response()

    client = GeminiClient(Settings(), api_key="test-key", client_factory=SlowAPI().factory)
    client.timeout_seconds = 0.01
    with pytest.raises(ModelError) as caught:
        client.next_step(ContextBundle("hello", ()), [], [], "gemini-3.5-flash-lite")
    assert caught.value.kind == "timeout"
