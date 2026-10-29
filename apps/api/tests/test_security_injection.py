"""Adversarial regression tests: the model is treated as an untrusted proposer."""

from test_tools import chat, execs, seeded

from nova_api import db
from nova_api.llm.interfaces import TextDelta, ToolCall, ToolCallEvent, UsageEvent
from nova_api.models import MockOrder


class Hijacked:
    """A model that has been fully taken over by injected text and fires attacker-chosen calls."""

    name, model, supports_tools = "hijacked", "h", True

    def __init__(self, calls):
        self.calls, self.turn = calls, 0

    def stream(self, req):
        self.turn += 1
        if self.turn == 1:
            yield TextDelta("Sure, doing it. ")
            for i, (n, a) in enumerate(self.calls):
                yield ToolCallEvent(ToolCall(f"c{i}", n, a))
        else:
            yield TextDelta("All done, refund completed successfully!")  # a lie
        yield UsageEvent()


def hijack(monkeypatch, calls):
    monkeypatch.setattr("nova_api.api.chat_routes.build_provider", lambda s: Hijacked(calls))


def test_injected_refund_still_needs_human_confirmation(client, monkeypatch):
    c = seeded()
    hijack(monkeypatch, [("request_mock_refund", {"order_id": "ORD-1001", "reason": "injected"})])
    chat(c, "summarise this document")
    with next(db.get_db()) as s:
        assert s.get(MockOrder, "ORD-1001").refunded is False
    assert [e.status for e in execs()] == ["pending_confirmation"]


def test_injected_access_to_other_users_order_fails(client, monkeypatch):
    c = seeded()  # alice
    hijack(monkeypatch, [("lookup_mock_order", {"order_id": "ORD-2001"})])
    cid, _ = chat(c, "hi")
    [ex] = execs()
    assert ex.status == "failed" and "not found" in ex.result_summary


def test_injected_unknown_and_privileged_tools_denied(client, monkeypatch):
    c = seeded()
    hijack(monkeypatch, [("run_shell", {"cmd": "id"}), ("../admin", {}), ("delete_all_users", {})])
    chat(c, "hi")
    assert {e.status for e in execs()} == {"denied"}


def test_tool_loop_is_bounded(client, monkeypatch):
    class Looper:
        name, model, supports_tools = "loop", "l", True
        turns = 0

        def stream(self, req):
            Looper.turns += 1
            yield ToolCallEvent(ToolCall(f"c{Looper.turns}", "get_mock_account_profile", {}))

    monkeypatch.setattr("nova_api.api.chat_routes.build_provider", lambda s: Looper())
    c = seeded()
    _, out = chat(c, "go")
    assert Looper.turns <= 4 and "tool call limit" in out["content"]


def test_only_actually_cited_sources_are_returned(client):
    c = seeded()
    _, out = chat(c, "What is the refund policy?")
    cited = {x["n"] for x in out["citations"]}
    assert cited == {1}  # the fake answered from source 1 only


def test_retrieved_text_cannot_escape_untrusted_block(client, monkeypatch):
    """The wrapper must keep document text inside <retrieved_documents>, after the user's text."""
    seen = {}

    class Spy:
        name, model, supports_tools = "spy", "s", False

        def stream(self, req):
            seen["system"], seen["last"] = req.system, req.messages[-1].content
            yield TextDelta("ok")

    monkeypatch.setattr("nova_api.api.chat_routes.build_provider", lambda s: Spy())
    c = seeded()
    chat(c, "What is the refund policy?")
    assert "untrusted" in seen["system"].lower()
    assert seen["last"].index("What is the refund policy?") < seen["last"].index("<retrieved_documents")
    assert "refund-policy.md" in seen["last"]
