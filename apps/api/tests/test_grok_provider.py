import json

import httpx
import pytest

from nova_api.llm.interfaces import (
    LLMError,
    LLMMessage,
    LLMRequest,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolSpec,
    UsageEvent,
)
from nova_api.llm.providers.grok import GrokProvider


def chunk(obj) -> str:
    return "data: " + json.dumps(obj)


SSE = "\n\n".join([
    chunk({"choices": [{"delta": {"role": "assistant", "content": "Hel"}}]}),
    chunk({"choices": [{"delta": {"content": "lo"}}]}),
    chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function",
           "function": {"name": "lookup_mock_order", "arguments": "{\"order_id\":"}}]}}]}),
    chunk({"choices": [{"delta": {"tool_calls": [{"index": 0,
           "function": {"arguments": "\"ORD-1001\"}"}}]}}]}),
    chunk({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
    chunk({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}}),
    "data: [DONE]",
])


def provider(handler):
    return GrokProvider("test-key", "grok-test", transport=httpx.MockTransport(handler))


def req():
    return LLMRequest("sys", [LLMMessage("user", "hi")],
                      [ToolSpec("lookup_mock_order", "d", {"type": "object"})])


def test_streams_text_tool_and_usage():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, text=SSE)

    events = list(provider(handler).stream(req()))
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello"
    call = next(e.call for e in events if isinstance(e, ToolCallEvent))
    assert call.name == "lookup_mock_order" and call.arguments == {"order_id": "ORD-1001"}
    assert isinstance(events[-1], UsageEvent) and (events[-1].input_tokens, events[-1].output_tokens) == (11, 7)
    assert seen["auth"] == "Bearer test-key" and seen["url"] == "https://api.x.ai/v1/chat/completions"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["tools"][0]["function"]["name"] == "lookup_mock_order"
    assert seen["body"]["stream"] is True


def test_tool_round_trip_message_format():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text="data: [DONE]")

    r = LLMRequest("sys", [
        LLMMessage("user", "q"),
        LLMMessage("assistant", "", tool_calls=[ToolCall("c1", "lookup_mock_order", {"order_id": "ORD-1"})]),
        LLMMessage("tool", "{\"status\":\"succeeded\"}", tool_call_id="c1"),
    ])
    list(provider(handler).stream(r))
    msgs = seen["body"]["messages"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == "{\"order_id\": \"ORD-1\"}"
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"status\":\"succeeded\"}"}


def test_malformed_tool_arguments_are_flagged_not_executed():
    bad = "\n\n".join([chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t", "function": {
        "name": "lookup_mock_order", "arguments": "{oops"}}]}}]}), "data: [DONE]"])
    call = next(e.call for e in provider(lambda r: httpx.Response(200, text=bad)).stream(req())
                if isinstance(e, ToolCallEvent))
    assert call.arguments == {"__invalid__": True}


@pytest.mark.parametrize("status,code", [(401, "auth"), (429, "rate_limit"), (400, "bad_request"),
                                         (503, "unavailable")])
def test_error_normalization(status, code):
    with pytest.raises(LLMError) as e:
        list(provider(lambda r: httpx.Response(status, json={"error": "secret detail"})).stream(req()))
    assert e.value.code == code and "secret" not in e.value.message


def test_timeout_normalized():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMError) as e:
        list(provider(handler).stream(req()))
    assert e.value.code == "timeout"


def test_missing_key_rejected():
    with pytest.raises(LLMError):
        GrokProvider("", "m")


def test_custom_base_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, text="data: [DONE]")

    p = GrokProvider("k", "m", base_url="http://localhost:9/v1/", transport=httpx.MockTransport(handler))
    list(p.stream(req()))
    assert seen["url"] == "http://localhost:9/v1/chat/completions"
