from test_tools import chat, seeded


def test_admin_health_hides_secrets(client):
    admin = seeded("admin@example.com")
    body = admin.get("/api/v1/admin/health").json()
    assert body["status"] == "ok" and "key" not in " ".join(k for k in body if k != "llm_key_configured")
    assert "sk-" not in str(body)


def test_admin_endpoints_forbidden_for_non_admins(client):
    for email in ("alice@example.com", "eval@example.com"):
        c = seeded(email)
        assert c.get("/api/v1/admin/health").status_code == 403
        assert c.get("/api/v1/admin/metrics").status_code == 403


def test_metrics_reflect_activity(client):
    alice = seeded()
    chat(alice, "hello")
    chat(alice, "Where is ORD-1001?")
    m = seeded("admin@example.com").get("/api/v1/admin/metrics").json()
    assert m["responses"] == 2
    assert m["tool_executions"].get("succeeded") == 1
    assert m["latency_ms"]["p50"] is not None and m["estimated_cost_usd"] is None


def test_evaluation_run_lifecycle(client):
    admin = seeded("admin@example.com")
    r = admin.post("/api/v1/admin/evaluations", json={"dataset": "tools"})
    assert r.status_code == 201 and r.json()["metrics"]["tool_selection_accuracy"] >= 0.95
    run_id = r.json()["id"]
    reader = seeded("eval@example.com")  # read-only evaluator
    assert reader.get(f"/api/v1/admin/evaluations/{run_id}").json()["id"] == run_id
    assert len(reader.get("/api/v1/admin/evaluations").json()) == 1
    assert reader.post("/api/v1/admin/evaluations", json={"dataset": "tools"}).status_code == 403
    assert seeded().get(f"/api/v1/admin/evaluations/{run_id}").status_code == 403


def test_evaluation_rejects_unknown_dataset(client):
    admin = seeded("admin@example.com")
    assert admin.post("/api/v1/admin/evaluations", json={"dataset": "../../etc"}).status_code == 422
