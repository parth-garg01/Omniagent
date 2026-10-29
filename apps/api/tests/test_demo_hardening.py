from fastapi.testclient import TestClient

from nova_api import db
from nova_api.config import get_settings
from nova_api.main import create_app
from nova_api.seed import seed


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("NOVA_ALLOW_REGISTRATION", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/api/v1/auth/register", json={"email": "n@example.com", "password": "correct-horse-1"})
        assert r.status_code == 403
    finally:
        get_settings.cache_clear()


def test_seed_uses_custom_password(client, monkeypatch):
    monkeypatch.setenv("NOVA_DEMO_PASSWORD", "a-very-different-pass-9")
    get_settings.cache_clear()
    try:
        with next(db.get_db()) as s:
            seed(s)
        c = TestClient(create_app())
        login = lambda pw: c.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": pw})  # noqa: E731
        assert login("demo-password-1").status_code == 401
        assert login("a-very-different-pass-9").status_code == 200
    finally:
        get_settings.cache_clear()


def test_seeded_short_password_can_log_in_but_cannot_be_registered(client, monkeypatch):
    monkeypatch.setenv("NOVA_DEMO_PASSWORD", "abc1234")
    get_settings.cache_clear()
    try:
        with next(db.get_db()) as s:
            seed(s)
        c = TestClient(create_app())
        assert c.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "abc1234"}).status_code == 200
        assert c.post("/api/v1/auth/register", json={"email": "n@example.com", "password": "abc1234"}).status_code == 422
    finally:
        get_settings.cache_clear()
