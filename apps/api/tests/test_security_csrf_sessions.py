from datetime import UTC, datetime, timedelta

import pytest
from conftest import register_login
from sqlalchemy import select

from nova_api import db
from nova_api.models import AuthSession

MUTATING = [
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/conversations"),
    ("patch", "/api/v1/conversations/x"),
    ("delete", "/api/v1/conversations/x"),
    ("post", "/api/v1/conversations/x/messages"),
    ("post", "/api/v1/conversations/x/cancel"),
    ("post", "/api/v1/messages/x/feedback"),
    ("delete", "/api/v1/documents/x"),
    ("post", "/api/v1/documents/x/reindex"),
    ("post", "/api/v1/tool-executions/x/confirm"),
    ("post", "/api/v1/tool-executions/x/cancel"),
    ("post", "/api/v1/admin/evaluations"),
]


@pytest.mark.parametrize("method,path", MUTATING)
def test_every_mutation_requires_csrf_token(client, method, path):
    register_login(client)
    del client.headers["X-CSRF-Token"]
    assert getattr(client, method)(path).status_code == 403
    client.headers["X-CSRF-Token"] = "wrong-token"
    assert getattr(client, method)(path).status_code == 403


@pytest.mark.parametrize("method,path", MUTATING)
def test_every_endpoint_requires_authentication(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_expired_session_rejected(client):
    register_login(client)
    with next(db.get_db()) as s:
        sess = s.scalar(select(AuthSession))
        sess.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        s.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_forged_session_cookie_rejected(client):
    client.cookies.set("nova_session", "A" * 43)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_session_cookie_flags(client):
    client.post("/api/v1/auth/register", json={"email": "c@example.com", "password": "correct-horse-1"})
    r = client.post("/api/v1/auth/login", json={"email": "c@example.com", "password": "correct-horse-1"})
    cookies = {h.split("=")[0]: h for h in r.headers.get_list("set-cookie")}
    assert "HttpOnly" in cookies["nova_session"] and "SameSite=lax" in cookies["nova_session"]
    assert "HttpOnly" not in cookies["nova_csrf"]  # the SPA must read it


def test_no_secret_material_in_responses(client):
    me = register_login(client)
    assert "password" not in str(me).lower()
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-1"})
    assert "argon2" not in r.text and "hashed" not in r.text


def test_login_does_not_reveal_whether_account_exists(client):
    client.post("/api/v1/auth/register", json={"email": "real@example.com", "password": "correct-horse-1"})
    a = client.post("/api/v1/auth/login", json={"email": "real@example.com", "password": "wrong-password"})
    b = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "wrong-password"})
    assert (a.status_code, a.json()) == (b.status_code, b.json())
