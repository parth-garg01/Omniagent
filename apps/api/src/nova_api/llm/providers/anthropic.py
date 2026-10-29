"""Anthropic Messages API adapter (httpx, SSE). Credentials come from server config only."""
import json
from collections.abc import Iterator

import httpx

from ..interfaces import (
    LLMError,
    LLMRequest,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    UsageEvent,
)

API_URL = "https://api.anthropic.com/v1/messages"


def _map_status(status: int) -> LLMError:
    if status in (401, 403):
        return LLMError("auth", "Provider rejected the configured credentials")
    if status == 429:
        return LLMError("rate_limit", "Provider rate limit reached")
    if status in (400, 404, 413, 422):
        return LLMError("bad_request", "Provider rejected the request")
    return LLMError("unavailable", "Provider is unavailable")


class AnthropicProvider:
    name = "anthropic"
    supports_tools = True

    def __init__(self, api_key: str, model: str, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError("auth", "NOVA_ANTHROPIC_API_KEY is not configured")
        self._key = api_key
        self.model = model
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _payload(self, req: LLMRequest) -> dict:
        msgs: list[dict] = []
        for m in req.messages:
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
                    msgs[-1]["content"].append(block)
                else:
                    msgs.append({"role": "user", "content": [block]})
            elif m.role == "assistant" and m.tool_calls:
                blocks = [{"type": "text", "text": m.content}] if m.content else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                           for c in m.tool_calls]
                msgs.append({"role": "assistant", "content": blocks})
            else:
                msgs.append({"role": m.role, "content": m.content})
        body: dict = {"model": self.model, "max_tokens": req.max_tokens, "system": req.system,
                      "messages": msgs, "stream": True}
        if req.tools:
            body["tools"] = [{"name": t.name, "description": t.description,
                              "input_schema": t.input_schema} for t in req.tools]
        return body

    def stream(self, request: LLMRequest) -> Iterator:
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        try:
            with self._client.stream("POST", API_URL, headers=headers,
                                     json=self._payload(request)) as r:
                if r.status_code >= 400:
                    r.read()
                    raise _map_status(r.status_code)
                yield from self._parse(r.iter_lines())
        except httpx.TimeoutException as e:
            raise LLMError("timeout", "Provider timed out") from e
        except httpx.HTTPError as e:
            raise LLMError("unavailable", "Could not reach provider") from e

    @staticmethod
    def _parse(lines) -> Iterator:
        tool: dict | None = None
        in_tok = out_tok = 0
        for line in lines:
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            t = ev.get("type")
            if t == "message_start":
                in_tok = ev.get("message", {}).get("usage", {}).get("input_tokens", 0)
            elif t == "content_block_start" and ev["content_block"]["type"] == "tool_use":
                cb = ev["content_block"]
                tool = {"id": cb["id"], "name": cb["name"], "json": ""}
            elif t == "content_block_delta":
                d = ev["delta"]
                if d["type"] == "text_delta":
                    yield TextDelta(d["text"])
                elif d["type"] == "input_json_delta" and tool is not None:
                    tool["json"] += d["partial_json"]
            elif t == "content_block_stop" and tool is not None:
                try:
                    args = json.loads(tool["json"] or "{}")
                except ValueError:
                    args = {"__invalid__": True}
                yield ToolCallEvent(ToolCall(tool["id"], tool["name"], args))
                tool = None
            elif t == "message_delta":
                out_tok = ev.get("usage", {}).get("output_tokens", out_tok)
            elif t == "error":
                code = "rate_limit" if ev.get("error", {}).get("type") == "rate_limit_error" else "unavailable"
                raise LLMError(code, "Provider reported an error")
        yield UsageEvent(in_tok, out_tok)
