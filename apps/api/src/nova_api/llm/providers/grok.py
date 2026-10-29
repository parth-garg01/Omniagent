"""Grok (xAI) adapter. xAI exposes an OpenAI-compatible chat completions API with SSE streaming.

Credentials come from server configuration only and are never sent to the client.
"""
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


def _map_status(status: int) -> LLMError:
    if status in (401, 403):
        return LLMError("auth", "Provider rejected the configured credentials")
    if status == 429:
        return LLMError("rate_limit", "Provider rate limit reached")
    if status in (400, 404, 413, 422):
        return LLMError("bad_request", "Provider rejected the request")
    return LLMError("unavailable", "Provider is unavailable")


class GrokProvider:
    name = "grok"
    supports_tools = True

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.x.ai/v1",
                 timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError("auth", "NOVA_GROK_API_KEY is not configured")
        self._key = api_key
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _payload(self, req: LLMRequest) -> dict:
        msgs: list[dict] = [{"role": "system", "content": req.system}]
        for m in req.messages:
            if m.role == "tool":
                msgs.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            elif m.role == "assistant" and m.tool_calls:
                msgs.append({"role": "assistant", "content": m.content or None, "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in m.tool_calls]})
            else:
                msgs.append({"role": m.role, "content": m.content})
        body: dict = {"model": self.model, "messages": msgs, "max_tokens": req.max_tokens,
                      "stream": True, "stream_options": {"include_usage": True}}
        if req.tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.input_schema}}
                for t in req.tools]
        return body

    def stream(self, request: LLMRequest) -> Iterator:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        try:
            with self._client.stream("POST", self._url, headers=headers,
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
        calls: dict[int, dict] = {}
        in_tok = out_tok = 0
        for line in lines:
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                ev = json.loads(payload)
            except ValueError:
                continue
            if ev.get("error"):
                code = "rate_limit" if ev["error"].get("type") == "rate_limit_error" else "unavailable"
                raise LLMError(code, "Provider reported an error")
            usage = ev.get("usage")
            if usage:
                in_tok = usage.get("prompt_tokens", in_tok)
                out_tok = usage.get("completion_tokens", out_tok)
            for choice in ev.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    yield TextDelta(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] = fn.get("name") or slot["name"]
                    slot["args"] += fn.get("arguments") or ""
        for i in sorted(calls):
            c = calls[i]
            try:
                args = json.loads(c["args"] or "{}")
            except ValueError:
                args = {"__invalid__": True}  # fails schema validation server-side
            yield ToolCallEvent(ToolCall(c["id"] or f"call_{i}", c["name"], args))
        yield UsageEvent(in_tok, out_tok)
