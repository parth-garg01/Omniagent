from conftest import make_client, register_login

from nova_api.config import get_settings


def small_limits(monkeypatch, msgs=3, uploads=2):
    monkeypatch.setenv("NOVA_RATE_LIMIT_MESSAGES", str(msgs))
    monkeypatch.setenv("NOVA_RATE_LIMIT_UPLOADS", str(uploads))
    get_settings.cache_clear()


def test_message_rate_limit(client, monkeypatch):
    small_limits(monkeypatch)
    register_login(client)
    cid = client.post("/api/v1/conversations").json()["id"]
    codes = [client.post(f"/api/v1/conversations/{cid}/messages",
                         json={"content": "x", "stream": False}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "x", "stream": False})
    assert int(r.headers["retry-after"]) >= 1
    get_settings.cache_clear()


def test_limit_is_per_user(client, monkeypatch):
    small_limits(monkeypatch, msgs=1)
    a, b = make_client("a@example.com"), make_client("b@example.com")
    ca, cb = (c.post("/api/v1/conversations").json()["id"] for c in (a, b))
    send = lambda c, cid: c.post(f"/api/v1/conversations/{cid}/messages",  # noqa: E731
                                 json={"content": "x", "stream": False}).status_code
    assert (send(a, ca), send(a, ca), send(b, cb)) == (200, 429, 200)
    get_settings.cache_clear()


def test_upload_rate_limit(client, monkeypatch):
    small_limits(monkeypatch)
    register_login(client)
    codes = [client.post("/api/v1/documents", files={"file": ("a.txt", b"hello world")}).status_code
             for _ in range(3)]
    assert codes == [201, 201, 429]
    get_settings.cache_clear()
