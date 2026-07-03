"""Copilot session history: store CRUD, route validation, audit action names."""
import pytest
from fastapi.testclient import TestClient

from app.main import app, _action_name
from app.store import Store, store

client = TestClient(app)
HDR = {"x-forwarded-email": "jason@example.com"}


def test_store_session_roundtrip_sql(monkeypatch):
    s = Store()
    s._ready = True
    calls = []

    def fake_exec(sql, params=None):
        calls.append((sql, params))

        class _R:
            result = type("D", (), {"data_array": [["abc", "home", "My chat", '{"turns":[]}']]})()

        return _R()

    monkeypatch.setattr(s, "_exec", fake_exec)
    s._save_session("u@x.com", "abc", "home", "My chat", '{"turns":[]}')
    sql, params = calls[0]
    assert "MERGE INTO" in sql and "ai_sessions" in sql
    assert params["id"] == "abc" and params["project"] == "home"

    got = s._get_session("u@x.com", "abc")
    assert got == {"id": "abc", "project": "home", "title": "My chat", "state": '{"turns":[]}'}

    s._delete_session("u@x.com", "abc")
    assert "DELETE FROM" in calls[-1][0]


def test_store_sessions_degrade(monkeypatch):
    s = Store()
    monkeypatch.setattr(s, "_ensure", lambda: False)
    assert s._list_sessions("u@x.com", "home") == []
    assert s._get_session("u@x.com", "abc") is None
    with pytest.raises(RuntimeError):
        s._save_session("u@x.com", "a", "home", "t", "{}")


def test_save_route_generates_id_and_titles(monkeypatch):
    saved = {}

    async def fake_save(user, sid, project, title, state):
        saved.update(user=user, id=sid, project=project, title=title, state=state)

    monkeypatch.setattr(store, "save_session", fake_save)
    r = client.put(
        "/api/copilot/sessions",
        json={"project": "home", "state": {"turns": [{"question": "hi"}], "outcomes": {}}},
        headers=HDR,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == saved["id"] and len(body["id"]) == 12
    assert body["title"] == "Untitled chat"  # no title sent
    assert saved["user"] == "jason@example.com"


def test_save_route_rejects_oversized_state(monkeypatch):
    called = []

    async def fake_save(*a):
        called.append(a)

    monkeypatch.setattr(store, "save_session", fake_save)
    r = client.put(
        "/api/copilot/sessions",
        json={"project": "home", "state": {"turns": ["x" * 500_000]}},
        headers=HDR,
    )
    assert r.status_code == 413 and not called


def test_detail_route_404_and_state_parse(monkeypatch):
    async def none(user, sid):
        return None

    monkeypatch.setattr(store, "get_session", none)
    assert client.get("/api/copilot/sessions/zzz", headers=HDR).status_code == 404

    async def bad_json(user, sid):
        return {"id": "a", "project": "home", "title": "t", "state": "{not json"}

    monkeypatch.setattr(store, "get_session", bad_json)
    r = client.get("/api/copilot/sessions/a", headers=HDR)
    assert r.status_code == 200 and r.json()["state"] == {}


def test_session_audit_action_names():
    assert _action_name("PUT", "/api/copilot/sessions") == "copilot.session.save"
    assert _action_name("DELETE", "/api/copilot/sessions/abc") == "copilot.session.delete"
