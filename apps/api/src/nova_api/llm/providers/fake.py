"""Deterministic offline provider used by tests and the default demo configuration.

It is NOT a language model: it applies fixed rules so the full pipeline (retrieval,
citations, tool calls, confirmation) can be exercised without network access.
"""
import json
import re
from collections.abc import Iterator

from ..interfaces import (
    LLMMessage,
    LLMRequest,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    UsageEvent,
)

ORDER_RE = re.compile(r"\bORD-\d{3,}\b", re.I)
SOURCE_RE = re.compile(r'<source n="(\d+)"[^>]*>(.*?)</source>', re.S)
ABSTAIN_HINTS = ("policy", "handbook", "document", "according to", "our company")


class FakeProvider:
    name = "fake"
    model = "fake-deterministic-1"
    supports_tools = True

    def stream(self, request: LLMRequest) -> Iterator:
        last = request.messages[-1]
        text, calls = self._decide(request, last)
        words = text.split(" ")
        for i, w in enumerate(words):
            yield TextDelta(w + (" " if i < len(words) - 1 else ""))
        for c in calls:
            yield ToolCallEvent(c)
        yield UsageEvent(input_tokens=sum(len(m.content) for m in request.messages) // 4,
                         output_tokens=max(1, len(text) // 4))

    def _decide(self, request: LLMRequest, last: LLMMessage) -> tuple[str, list[ToolCall]]:
        if last.role == "tool":
            return self._summarize_tool(last.content), []
        q = last.content.split("<retrieved_documents", 1)[0].strip()
        low = q.lower()
        allowed = {t.name for t in request.tools}
        order = ORDER_RE.search(q)

        def call(name: str, args: dict) -> tuple[str, list[ToolCall]]:
            if name not in allowed:
                return "That action is not available to me right now.", []
            return "", [ToolCall(id=f"call_{name}", name=name, arguments=args)]

        if "refund" in low and order:
            return call("request_mock_refund", {"order_id": order.group(0).upper(),
                                                "reason": "customer request"})
        if order:
            return call("lookup_mock_order", {"order_id": order.group(0).upper()})
        if "ticket" in low:
            return call("create_mock_support_ticket", {"subject": q[:80], "body": q})
        if "my account" in low or "my profile" in low:
            return call("get_mock_account_profile", {})
        sources = SOURCE_RE.findall(last.content)
        if sources:
            n, body = sources[0]
            return f"{body.strip()[:300]} [{n}]", []
        if any(h in low for h in ABSTAIN_HINTS):
            return ("I couldn't find enough information in the knowledge base to answer that. "
                    "Could you share more detail or upload the relevant document?"), []
        return f"You said: {q[:200]}", []

    @staticmethod
    def _summarize_tool(content: str) -> str:
        try:
            data = json.loads(content)
        except ValueError:
            return "The tool returned an unreadable result."
        status = data.get("status", "unknown")
        msg = data.get("message", "")
        if status == "pending_confirmation":
            return f"This needs your confirmation before I proceed. {msg}"
        if status != "succeeded":
            return f"The action did not complete (status: {status}). {msg}"
        return f"Done (status: succeeded). {msg}"
