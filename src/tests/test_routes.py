"""BFF route behavior: error mapping, validation, and search/builder plumbing —
TestClient over the real app with the ADO/warehouse clients monkeypatched."""
import httpx
import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.main import app

client = TestClient(app)


@pytest.fixture
def ado(monkeypatch):
    """Replace ADOClient with a configurable fake; tests set attributes on it."""

    class Fake:
        pass

    fake = Fake()
    monkeypatch.setattr(routes, "ADOClient", lambda: fake)
    return fake


# ---- _call error mapping -------------------------------------------------------------


def test_ado_config_error_maps_to_503(monkeypatch):
    def boom():
        raise routes.ADOConfigError("ADO_ORG_URL and ADO_PAT must be set")

    monkeypatch.setattr(routes, "ADOClient", boom)
    r = client.get("/api/projects")
    assert r.status_code == 503 and "ADO_ORG_URL" in r.json()["detail"]


def test_upstream_status_maps_through(ado):
    async def fails():
        resp = httpx.Response(404, request=httpx.Request("GET", "http://x"))
        raise httpx.HTTPStatusError("nope", request=resp.request, response=resp)

    ado.list_projects = fails
    r = client.get("/api/projects")
    assert r.status_code == 404 and "404" in r.json()["detail"]


def test_network_error_maps_to_502(ado):
    async def fails():
        raise httpx.ConnectError("boom")

    ado.list_projects = fails
    assert client.get("/api/projects").status_code == 502


# ---- write validation -----------------------------------------------------------------


def test_create_work_item_requires_type_and_title(ado):
    r = client.post("/api/projects/p/workitems", json={"type": " ", "title": "x"})
    assert r.status_code == 422
    r = client.post("/api/projects/p/workitems", json={"type": "Task", "title": ""})
    assert r.status_code == 422


def test_update_work_item_requires_some_field(ado):
    assert client.patch("/api/projects/p/workitems/3", json={}).status_code == 422


def test_update_work_item_empty_assignee_clears(ado):
    seen = {}

    async def upd(wid, fields):
        seen[wid] = fields
        return {}

    async def get(wid):
        return {"id": wid}

    ado.update_work_item = upd
    ado.get_work_item = get
    r = client.patch("/api/projects/p/workitems/3", json={"assignedTo": ""})
    assert r.status_code == 200
    assert seen[3] == {"System.AssignedTo": None}  # explicit empty → remove op


def test_pr_thread_validation(ado):
    r = client.post("/api/projects/p/repos/r/pullrequests/1/threads", json={"comment": "  "})
    assert r.status_code == 422
    r = client.post(
        "/api/projects/p/repos/r/pullrequests/1/threads",
        json={"comment": "hi", "line": 4},  # line without a file
    )
    assert r.status_code == 422


# ---- global search route ----------------------------------------------------------------


def test_search_rejects_short_query(ado):
    assert client.get("/api/projects/p/search?q=a").status_code == 422


def test_search_planes_fail_independently(ado, monkeypatch):
    async def wi_fails(project, query, top):
        raise httpx.ConnectError("search down")

    ado.search_work_items = wi_fails

    async def code_ok(project, query, c):
        return {"available": True, "results": [], "indexedFiles": 5}

    monkeypatch.setattr(routes.codesearch.code_search, "search", code_ok)
    r = client.get("/api/projects/p/search?q=genie")
    assert r.status_code == 200
    d = r.json()
    assert d["workItems"]["available"] is False
    assert d["code"]["available"] is True


# ---- report builder routes ------------------------------------------------------------


def test_builder_run_rejects_bad_definition():
    r = client.post("/api/reports/builder/run", json={"dimensions": ["nope"], "measures": ["items"]})
    assert r.status_code == 422 and "unknown fields" in r.json()["detail"]


def test_builder_run_maps_unavailable_to_503(monkeypatch):
    async def unavailable(d):
        raise RuntimeError("no SQL warehouse visible to the app")

    monkeypatch.setattr(routes.reportbuilder.builder, "run", unavailable)
    r = client.post("/api/reports/builder/run", json={"dimensions": [], "measures": ["items"]})
    assert r.status_code == 503


def test_saved_report_requires_name():
    r = client.put("/api/reports/saved", json={"name": " ", "definition": {}})
    assert r.status_code == 422


# ---- misc -------------------------------------------------------------------------------


def test_genie_unconfigured_is_503():
    r = client.post("/api/genie/ask", json={"question": "hi"})
    assert r.status_code == 503


def test_health_shape():
    d = client.get("/api/health").json()
    assert set(d) >= {"status", "ado_configured", "genie_configured", "copilot_configured"}
