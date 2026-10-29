from fastapi.testclient import TestClient

from nova_api.main import create_app


def test_health():
    r = TestClient(create_app()).get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
