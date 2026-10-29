from conftest import register_login
from fastapi.testclient import TestClient
from sqlalchemy import select

from nova_api import db
from nova_api.main import create_app
from nova_api.models import AuthSession, User

PW = "correct-horse-1"


def test_register_login_me_logout(client):
    register_login(client)
    assert client.get("/api/v1/auth/me").json()["email"] == "a@example.com"
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_role_cannot_be_forged_on_register(client):
    r = client.post("/api/v1/auth/register",
                    json={"email": "x@example.com", "password": PW, "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "user"


def test_password_is_argon2id_and_token_stored_hashed(client):
    register_login(client)
    raw = client.cookies.get("nova_session")
    with next(db.get_db()) as s:
        assert s.scalar(select(User)).password_hash.startswith("$argon2id$")
        assert s.scalar(select(AuthSession)).hashed_token != raw


def test_revoked_session_rejected(client):
    register_login(client)
    with next(db.get_db()) as s:
        from datetime import UTC, datetime
        sess = s.scalar(select(AuthSession))
        sess.revoked_at = datetime.now(UTC)
        s.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_for_mutations(client):
    register_login(client)
    del client.headers["X-CSRF-Token"]
    assert client.post("/api/v1/auth/logout").status_code == 403


def test_login_throttled(client):
    client.post("/api/v1/auth/register", json={"email": "t@example.com", "password": PW})
    c = TestClient(create_app())
    codes = [c.post("/api/v1/auth/login", json={"email": "t@example.com", "password": "wrong-pass-1"}).status_code
             for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # even the right password is blocked while throttled
    assert c.post("/api/v1/auth/login", json={"email": "t@example.com", "password": PW}).status_code == 429
