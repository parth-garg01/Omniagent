import pytest
from fastapi.testclient import TestClient

from nova_api import db
from nova_api.auth.security import throttle
from nova_api.main import create_app


@pytest.fixture()
def client():
    db.init_db("sqlite://")
    throttle.reset()
    return TestClient(create_app())


def register_login(client: TestClient, email="a@example.com", password="correct-horse-1"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = client.cookies.get("nova_csrf")
    return r.json()


def make_client(email: str) -> TestClient:
    c = TestClient(create_app())
    register_login(c, email)
    return c
