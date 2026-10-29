import json

from sqlalchemy import select

from nova_api import db
from nova_api.models import AuditEvent, MockOrder, MockTicket, ToolExecution, User
from nova_api.seed import seed


def seeded(email="alice@example.com"):
    with next(db.get_db()) as s:
        seed(s)
    from fastapi.testclient import TestClient

    from nova_api.main import create_app
    c = TestClient(create_app())
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "demo-password-1"}).status_code == 200
    c.headers["X-CSRF-Token"] = c.cookies.get("nova_csrf")
    return c


def chat(c, text, cid=None):
    cid = cid or c.post("/api/v1/conversations").json()["id"]
    r = c.post(f"/api/v1/conversations/{cid}/messages", json={"content": text, "stream": False})
    return cid, r.json()


def execs():
    with next(db.get_db()) as s:
        return s.scalars(select(ToolExecution)).all()


def test_order_lookup_reports_real_tool_result(client):
    c = seeded()
    _, out = chat(c, "Where is ORD-1002?")
    assert "shipped" in out["content"] and "succeeded" in out["content"]
    assert [e.tool_name for e in execs()] == ["lookup_mock_order"]


def test_cannot_look_up_another_users_order(client):
    c = seeded("bob@example.com")
    _, out = chat(c, "Status of ORD-1001?")
    assert "not found" in out["content"] and "failed" in out["content"]


def test_refund_requires_confirmation_then_executes_once(client):
    c = seeded()
    cid, out = chat(c, "Please refund ORD-1001")
    assert "confirmation" in out["content"]
    [ex] = execs()
    assert ex.status == "pending_confirmation"
    with next(db.get_db()) as s:
        assert s.get(MockOrder, "ORD-1001").refunded is False  # nothing happened yet
    assert c.post(f"/api/v1/tool-executions/{ex.id}/confirm").json()["status"] == "succeeded"
    assert c.post(f"/api/v1/tool-executions/{ex.id}/confirm").status_code == 409  # no double run
    with next(db.get_db()) as s:
        assert s.get(MockOrder, "ORD-1001").refunded is True
    last = c.get(f"/api/v1/conversations/{cid}").json()["messages"][-1]
    assert last["content"].startswith("Confirmed.")


def test_duplicate_refund_request_is_deduplicated(client):
    c = seeded()
    chat(c, "refund ORD-1001")
    chat(c, "refund ORD-1001 again")
    assert len(execs()) == 1


def test_cancel_pending_refund(client):
    c = seeded()
    chat(c, "refund ORD-1001")
    [ex] = execs()
    assert c.post(f"/api/v1/tool-executions/{ex.id}/cancel").json()["status"] == "cancelled"
    assert c.post(f"/api/v1/tool-executions/{ex.id}/confirm").status_code == 409
    with next(db.get_db()) as s:
        assert s.get(MockOrder, "ORD-1001").refunded is False


def test_other_user_cannot_confirm_execution(client):
    alice = seeded()
    chat(alice, "refund ORD-1001")
    [ex] = execs()
    bob = seeded("bob@example.com")
    assert bob.post(f"/api/v1/tool-executions/{ex.id}/confirm").status_code == 404
    assert bob.post(f"/api/v1/tool-executions/{ex.id}/cancel").status_code == 404


def test_refund_of_non_delivered_order_fails_at_confirm(client):
    c = seeded()
    chat(c, "refund ORD-1002")
    [ex] = execs()
    assert c.post(f"/api/v1/tool-executions/{ex.id}/confirm").json()["status"] == "failed"


def test_ticket_created_with_redacted_arguments(client):
    c = seeded()
    chat(c, "Open a ticket: my headphones are broken " + "." * 80 + " SECRET-DETAIL")
    [ex] = execs()
    assert ex.status == "succeeded" and "SECRET-DETAIL" not in json.dumps(ex.arguments)
    with next(db.get_db()) as s:
        assert len(s.scalars(select(MockTicket)).all()) == 1


def test_profile_tool(client):
    c = seeded()
    _, out = chat(c, "show my account")
    assert "alice@example.com" in out["content"]


def test_evaluator_role_cannot_use_tools(client):
    c = seeded("eval@example.com")
    assert c.get("/api/v1/tools").status_code == 403
    _, out = chat(c, "Where is ORD-1001?")
    assert "not available" in out["content"] and execs() == []


def test_tool_listing_has_metadata(client):
    c = seeded()
    tools = {t["name"]: t for t in c.get("/api/v1/tools").json()}
    assert set(tools) == {"search_knowledge_base", "lookup_mock_order", "get_mock_account_profile",
                          "create_mock_support_ticket", "request_mock_refund"}
    assert tools["request_mock_refund"]["requires_confirmation"] is True


def test_registry_rejects_forged_and_invalid_calls(client):
    """Direct registry calls simulate a compromised/hallucinating model."""
    from nova_api.llm.interfaces import ToolCall
    from nova_api.tools.mock_tools import build_registry

    seeded()
    reg = build_registry()
    with next(db.get_db()) as s:
        alice = s.scalar(select(User).where(User.email == "alice@example.com"))
        conv_id = "c"
        for call, expect in [
            (ToolCall("1", "delete_everything", {}), "denied"),
            (ToolCall("2", "lookup_mock_order", {"order_id": "ORD-1001; DROP TABLE"}), "failed"),
            (ToolCall("3", "lookup_mock_order", {}), "failed"),
            (ToolCall("4", "request_mock_refund", {"order_id": "ORD-1001", "reason": "x" * 999}), "failed"),
        ]:
            assert reg.execute(s, alice, conv_id, None, call).status == expect
    assert not any(e.status == "succeeded" for e in execs())


def test_audit_events_written(client):
    c = seeded()
    chat(c, "Where is ORD-1001?")
    with next(db.get_db()) as s:
        assert any(a.action == "tool.lookup_mock_order" for a in s.scalars(select(AuditEvent)))


def test_seeded_shared_docs_visible_to_all(client):
    c = seeded()
    _, out = chat(c, "What is the refund policy?")
    assert out["citations"] and out["citations"][0]["filename"] == "refund-policy.md"


def test_seed_is_idempotent(client):
    seeded()
    seeded()
    with next(db.get_db()) as s:
        assert len(s.scalars(select(User)).all()) == 4
