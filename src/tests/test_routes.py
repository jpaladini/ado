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

    async def prs_ok(project, query, top=10):
        return [{"id": 9, "title": "genie fix", "status": "active", "isDraft": False}]

    ado.search_pull_requests = prs_ok

    async def code_ok(project, query, c):
        return {"available": True, "results": [], "indexedFiles": 5}

    monkeypatch.setattr(routes.codesearch.code_search, "search", code_ok)
    r = client.get("/api/projects/p/search?q=genie")
    assert r.status_code == 200
    d = r.json()
    assert d["workItems"]["available"] is False
    assert d["pullRequests"]["available"] is True
    assert d["pullRequests"]["results"][0]["id"] == 9
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


# ---- simple GET routes through the fake client -------------------------------------


def test_simple_get_routes_map_client_calls(ado):
    async def one(*a, **kw):
        return [{"id": 1}]

    async def detail(*a, **kw):
        return {"id": 9}

    for attr in ("list_projects", "list_work_items", "list_work_item_types",
                 "list_iterations", "list_pull_requests", "list_builds", "list_repos",
                 "list_commits", "list_branches", "get_tree", "list_work_item_comments",
                 "search_identities", "list_pr_threads"):
        setattr(ado, attr, one)
    ado.get_work_item = detail
    ado.get_file = detail
    ado.connection_data = detail
    ado.pr_files = detail

    assert client.get("/api/projects").json() == {"value": [{"id": 1}]}
    assert client.get("/api/me").json() == {"id": 9}
    assert client.get("/api/projects/p/workitems").json()["value"]
    assert client.get("/api/projects/p/workitems/9").json() == {"id": 9}
    assert client.get("/api/projects/p/workitems/9/comments").json()["value"]
    assert client.get("/api/projects/p/workitemtypes").json()["value"]
    assert client.get("/api/projects/p/iterations").json()["value"]
    assert client.get("/api/identities?q=ja").json()["value"]
    assert client.get("/api/projects/p/pullrequests").json()["value"]
    assert client.get("/api/projects/p/builds").json()["value"]
    assert client.get("/api/projects/p/repos").json()["value"]
    assert client.get("/api/projects/p/repos/r/commits").json()["value"]
    assert client.get("/api/projects/p/repos/r/branches").json()["value"]
    assert client.get("/api/projects/p/repos/r/tree?branch=dev").json()["value"]
    assert client.get("/api/projects/p/repos/r/file?path=/a&branch=dev").json() == {"id": 9}
    assert client.get("/api/projects/p/repos/r/pullrequests/3/files").json() == {"id": 9}
    assert client.get("/api/projects/p/repos/r/pullrequests/3/threads").json()["value"]


def test_work_item_writes_route_through_client(ado):
    captured = {}

    async def create(project, wtype, fields):
        captured["create"] = (wtype, fields)
        return {"id": 100}

    async def comment(project, wid, text):
        captured["comment"] = (wid, text)
        return {"id": 1}

    async def state(wid, fields):
        captured["state"] = (wid, fields)
        return {"id": wid}

    ado.create_work_item = create
    ado.add_work_item_comment = comment
    ado.update_work_item = state

    r = client.post("/api/projects/p/workitems",
                    json={"type": "Task", "title": "T", "description": "d"})
    assert r.status_code == 200 and captured["create"][0] == "Task"
    assert captured["create"][1]["System.Title"] == "T"

    r = client.post("/api/projects/p/workitems/5/comments", json={"text": "hi"})
    assert r.status_code == 200 and captured["comment"] == (5, "hi")

    r = client.patch("/api/projects/p/workitems/5/state", json={"state": "Doing"})
    assert r.status_code == 200 and captured["state"] == (5, {"System.State": "Doing"})


def test_pr_vote_resolves_reviewer_then_votes(ado):
    order = []

    async def me():
        order.append("me")
        return {"id": "u-1", "displayName": "Jason"}

    async def vote(project, rid, pr_id, reviewer, v):
        order.append(("vote", reviewer, v))
        return {"vote": v}

    ado.connection_data = me
    ado.set_pr_vote = vote
    r = client.put("/api/projects/p/repos/r/pullrequests/2/vote", json={"vote": 10})
    assert r.status_code == 200 and order == ["me", ("vote", "u-1", 10)]


def test_pr_status_route(ado):
    async def set_status(project, rid, pr_id, status):
        return {"status": status}

    ado.set_pr_status = set_status
    r = client.patch("/api/projects/p/repos/r/pullrequests/2", json={"status": "abandoned"})
    assert r.json() == {"status": "abandoned"}


# ---- analytics + reports routes -------------------------------------------------------


@pytest.fixture
def analytics(monkeypatch):
    class FakeAnalytics:
        async def count_by_state_category(self, project):
            return {"Proposed": 2, "InProgress": 1, "Completed": 3}

        async def open_trend(self, project, days):
            return [{"date": "2026-07-01", "count": 3}]

        async def created_per_day(self, *a, **kw):
            return [{"dateSK": 20260701, "count": 2}]

        async def completed_per_day(self, *a, **kw):
            return [{"dateSK": 20260702, "count": 1}]

        async def cycle_time_items(self, *a, **kw):
            return [{"id": 1, "title": "t", "type": "Issue", "cycleBdays": 2,
                     "leadBdays": 3, "closedDate": "2026-07-02"}]

        async def cfd(self, *a, **kw):
            return [{"date": "2026-07-01", "category": "Proposed", "count": 2}]

        async def open_items_detail(self, *a, **kw):
            return [{"id": 2, "title": "o", "type": "Issue", "state": "Doing",
                     "category": "InProgress", "assignee": None, "ageBdays": 4}]

    monkeypatch.setattr(routes, "AnalyticsClient", FakeAnalytics)
    return FakeAnalytics


def test_analytics_route_aggregates(analytics):
    d = client.get("/api/projects/p/analytics?range=7d").json()
    assert d["open"] == 3 and d["total"] == 6 and d["available"] is True
    assert d["trend"][0]["count"] == 3


def test_reports_route_kpis_in_business_days(analytics):
    d = client.get("/api/projects/p/reports?range=30d&types=Issue,%20Task").json()
    k = d["kpis"]
    assert (k["throughput"], k["created"], k["netFlow"], k["wip"]) == (1, 2, 1, 1)
    assert k["cycleP50"] == 2.0 and d["durationUnit"] == "businessDays"
    assert d["filters"]["types"] == ["Issue", "Task"]


def test_reports_export_routes(analytics):
    r = client.get("/api/projects/p/reports/export?format=xlsx")
    assert r.status_code == 200 and r.headers["content-type"].endswith("sheet")
    assert 'filename="flow-metrics-p-30d.xlsx"' in r.headers["content-disposition"]
    r = client.get("/api/projects/p/reports/export?format=pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert client.get("/api/projects/p/reports/export?format=docx").status_code == 422


def test_table_export_route_validation():
    # "/" is illegal in both filenames and xlsx sheet titles — must be sanitized
    r = client.post("/api/export/table",
                    json={"name": "t/x", "columns": ["a"], "rows": [[1]]})
    assert r.status_code == 200
    assert 'filename="t_x.xlsx"' in r.headers["content-disposition"]
    bad = client.post("/api/export/table", json={"name": "t", "columns": [], "rows": []})
    assert bad.status_code == 422
