import json

import httpx
import pytest

from nova_api.llm.interfaces import (
    LLMError,
    LLMMessage,
    LLMRequest,
    TextDelta,
    ToolCallEvent,
    ToolSpec,
)
from nova_api.llm.providers.anthropic import AnthropicProvider

SSE = "\n".join([
    'data: {"type":"message_start","message":{"usage":{"input_tokens":11}}}',
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hel"}}',
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}',
    'data: {"type":"content_block_start","content_block":{"type":"tool_use","id":"t1","name":"lookup_mock_order"}}',
    'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{\\"order_id\\":"}}',
    'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"\\"ORD-1001\\"}"}}',
    'data: {"type":"content_block_stop"}',
    'data: {"type":"message_delta","usage":{"output_tokens":7}}',
])


def provider(handler):
    return AnthropicProvider("test-key", "m", transport=httpx.MockTransport(handler))


def req():
    return LLMRequest("sys", [LLMMessage("user", "hi")],
                      [ToolSpec("lookup_mock_order", "d", {"type": "object"})])


def test_streams_text_tool_and_usage():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["key"] = request.headers["x-api-key"]
        return httpx.Response(200, text=SSE)

    events = list(provider(handler).stream(req()))
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello"
    call = next(e.call for e in events if isinstance(e, ToolCallEvent))
    assert call.name == "lookup_mock_order" and call.arguments == {"order_id": "ORD-1001"}
    assert (events[-1].input_tokens, events[-1].output_tokens) == (11, 7)
    assert seen["key"] == "test-key" and seen["body"]["tools"][0]["name"] == "lookup_mock_order"


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
        AnthropicProvider("", "m")
