"""Identity headers, whoami, settings validation, and audit middleware."""
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)
HDR = {"x-forwarded-email": "jason@example.com"}


def test_whoami_with_forwarded_header():
    r = client.get("/api/whoami", headers=HDR)
    assert r.status_code == 200
    d = r.json()
    assert d["user"] == "jason@example.com"
    assert d["source"] == "x-forwarded-email"
    assert "store" in d


def test_whoami_local_fallback():
    d = client.get("/api/whoami").json()
    assert d["user"] == "local" and d["source"] == "none"


def test_put_setting_rejects_empty_key():
    r = client.put("/api/settings", json={"key": "  ", "value": "x"}, headers=HDR)
    assert r.status_code == 422


def test_audit_middleware_captures_mutations(monkeypatch):
    events = []
    monkeypatch.setattr(store, "audit", lambda **kw: events.append(kw))

    client.post("/api/genie/ask", json={"question": "hi"}, headers=HDR)  # 503 (unconfigured) still audited
    client.get("/api/health", headers=HDR)  # GET — not audited

    assert len(events) == 1
    e = events[0]
    assert e["user"] == "jason@example.com"
    assert e["action"] == "genie.ask"
    assert e["status"] == 503
    assert "hi" in e["detail"]


def test_action_names():
    from app.main import _action_name

    assert _action_name("PATCH", "/api/projects/p/workitems/31/state") == "workitem.state"
    assert _action_name("POST", "/api/projects/p/workitems/31/comments") == "workitem.comment"
    assert _action_name("PUT", "/api/projects/p/repos/r/pullrequests/7/vote") == "pr.approve"
    assert _action_name("PATCH", "/api/projects/p/repos/r/pullrequests/7") == "pr.status"
    assert _action_name("POST", "/api/analytics/refresh") == "analytics.refresh"
    assert _action_name("DELETE", "/api/other") == "delete /api/other"