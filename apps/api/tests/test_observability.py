import json
import logging

from conftest import register_login

from nova_api.observability.logging import JsonFormatter, redact, request_id_var


def test_redact_secrets():
    out = redact('password=hunter2 api_key: sk-abcdef123456 token="abc.def" hello')
    assert "hunter2" not in out and "sk-abcdef123456" not in out and "abc.def" not in out
    assert "hello" in out


def test_json_formatter_includes_request_id_and_redacts():
    request_id_var.set("req-1")
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "login password=s3cret", None, None)
    data = json.loads(JsonFormatter().format(rec))
    assert data["request_id"] == "req-1" and "s3cret" not in data["msg"]


def test_response_has_request_id(client):
    assert client.get("/api/v1/health").headers["X-Request-ID"]


def test_spans_logged_without_payloads(client, caplog):
    caplog.set_level(logging.INFO, logger="nova.trace")
    register_login(client)
    cid = client.post("/api/v1/conversations").json()["id"]
    client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "TOP-SECRET-PAYLOAD", "stream": False})
    spans = [r.fields["span"] for r in caplog.records if hasattr(r, "fields")]
    assert {"retrieval", "provider"} <= set(spans)
    assert "TOP-SECRET-PAYLOAD" not in json.dumps([r.fields for r in caplog.records if hasattr(r, "fields")])


def test_security_headers_present(client):
    h = client.get("/api/v1/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
