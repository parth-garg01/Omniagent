import json

from conftest import make_client, register_login

from nova_api.llm.interfaces import LLMError


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0][7:], json.loads(lines[1][6:])))
    return out


def new_conv(c):
    return c.post("/api/v1/conversations").json()["id"]


def test_stream_persist_and_resume(client):
    register_login(client)
    cid = new_conv(client)
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hello there"})
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "user_message" and names[-1] == "done" and "delta" in names
    streamed = "".join(d["text"] for e, d in events if e == "delta")
    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == streamed == "You said: hello there"
    assert detail["title"] == "hello there"


def test_non_streaming_mode(client):
    register_login(client)
    cid = new_conv(client)
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hi", "stream": False})
    assert r.status_code == 200 and r.json()["content"] == "You said: hi"


def test_retry_with_same_client_message_id_does_not_duplicate(client):
    register_login(client)
    cid = new_conv(client)
    body = {"content": "once", "client_message_id": "abc"}
    client.post(f"/api/v1/conversations/{cid}/messages", json=body)
    r = client.post(f"/api/v1/conversations/{cid}/messages", json=body)
    assert parse_sse(r.text)[-1][1].get("replayed") is True
    assert len(client.get(f"/api/v1/conversations/{cid}").json()["messages"]) == 2


def test_conversation_ownership_isolated():
    a, b = make_client("a@example.com"), make_client("b@example.com")
    cid = new_conv(a)
    assert b.get(f"/api/v1/conversations/{cid}").status_code == 404
    assert b.post(f"/api/v1/conversations/{cid}/messages", json={"content": "x"}).status_code == 404
    assert b.patch(f"/api/v1/conversations/{cid}", json={"title": "z"}).status_code == 404
    assert b.delete(f"/api/v1/conversations/{cid}").status_code == 404
    assert b.post(f"/api/v1/conversations/{cid}/cancel").status_code == 404
    assert cid not in [c["id"] for c in b.get("/api/v1/conversations").json()]


def test_rename_delete(client):
    register_login(client)
    cid = new_conv(client)
    assert client.patch(f"/api/v1/conversations/{cid}", json={"title": "T"}).json()["title"] == "T"
    assert client.delete(f"/api/v1/conversations/{cid}").status_code == 204
    assert client.get(f"/api/v1/conversations/{cid}").status_code == 404


def test_oversized_message_rejected(client):
    register_login(client)
    cid = new_conv(client)
    assert client.post(f"/api/v1/conversations/{cid}/messages",
                       json={"content": "x" * 5000}).status_code == 413


def test_feedback_only_on_own_messages():
    a, b = make_client("a@example.com"), make_client("b@example.com")
    cid = new_conv(a)
    a.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hi", "stream": False})
    mid = a.get(f"/api/v1/conversations/{cid}").json()["messages"][1]["id"]
    assert b.post(f"/api/v1/messages/{mid}/feedback", json={"value": "up"}).status_code == 404
    assert a.post(f"/api/v1/messages/{mid}/feedback", json={"value": "up"}).status_code == 204


def test_provider_error_is_persisted_and_normalized(client, monkeypatch):
    class Boom:
        name, model, supports_tools = "boom", "b", False

        def stream(self, req):
            raise LLMError("rate_limit", "Provider rate limit reached")
            yield

    monkeypatch.setattr("nova_api.api.chat_routes.build_provider", lambda s: Boom())
    register_login(client)
    cid = new_conv(client)
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hi"})
    names = dict(parse_sse(r.text))
    assert names["error"]["code"] == "rate_limit"
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"][1]["status"] == "error"


def test_unauthenticated_rejected(client):
    assert client.post("/api/v1/conversations").status_code == 401


def test_concurrent_duplicate_client_id_is_reported_not_crashed(client):
    """Regression for #2: losing the unique-constraint race must be treated as a retry."""
    from nova_api import db
    from nova_api.models import Conversation
    from nova_api.orchestration.engine import DuplicateMessage, add_message

    register_login(client)
    cid = new_conv(client)
    with next(db.get_db()) as s:
        conv = s.get(Conversation, cid)
        first = add_message(s, conv, "user", "a", client_message_id="X")
        try:
            add_message(s, conv, "user", "a", client_message_id="X")
            raise AssertionError("expected DuplicateMessage")
        except DuplicateMessage as d:
            assert d.existing.id == first.id
