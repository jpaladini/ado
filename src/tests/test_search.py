"""Global search: work-item search fallback chain and the BFF code index."""
import httpx
import pytest

from app.ado.client import ADOClient
from app.codesearch import CodeSearch, _indexable, _looks_minified


# ---- work items -------------------------------------------------------------------


def _client() -> ADOClient:
    return ADOClient(org_url="https://dev.azure.com/myorg", pat="x")


@pytest.mark.asyncio
async def test_search_work_items_falls_back_to_wiql(monkeypatch):
    c = _client()

    async def alm_fails(project, query, top):
        raise httpx.ConnectError("almsearch down")

    wiql_calls = []

    async def wiql_ok(project, query, top):
        wiql_calls.append(query)
        return [{"id": 7, "title": "t", "type": "Task", "state": "New",
                 "assignedTo": None, "snippet": None}]

    monkeypatch.setattr(c, "_search_work_items_alm", alm_fails)
    monkeypatch.setattr(c, "_search_work_items_wiql", wiql_ok)
    out = await c.search_work_items("Demo", "genie")
    assert out[0]["id"] == 7 and wiql_calls == ["genie"]


@pytest.mark.asyncio
async def test_wiql_search_escapes_quotes_and_maps_fields(monkeypatch):
    c = _client()
    captured = {}

    async def fake_post(path, body, params=None):
        captured["wiql"] = body["query"]
        return {"workItems": [{"id": 3}]}

    async def fake_get(path, params=None):
        captured["ids"] = params["ids"]
        return {"value": [{"id": 3, "fields": {
            "System.Title": "Fix o'clock bug", "System.WorkItemType": "Bug",
            "System.State": "Active",
            "System.AssignedTo": {"displayName": "Ada"}}}]}

    monkeypatch.setattr(c, "_post", fake_post)
    monkeypatch.setattr(c, "_get", fake_get)
    out = await c._search_work_items_wiql("Demo", "o'clock", 10)
    assert "''" in captured["wiql"]  # single quote doubled — no WIQL breakage
    assert captured["ids"] == "3"
    assert out == [{"id": 3, "title": "Fix o'clock bug", "type": "Bug",
                    "state": "Active", "assignedTo": "Ada", "snippet": None}]


@pytest.mark.asyncio
async def test_search_pull_requests_filters_and_dedupes(monkeypatch):
    c = _client()
    active = [
        {"id": 22, "title": "Global search", "sourceRef": "claude/x", "targetRef": "dev",
         "createdBy": "Jason", "repository": "ado", "status": "active", "isDraft": False},
        {"id": 30, "title": "Unrelated", "sourceRef": "f", "targetRef": "dev",
         "createdBy": "Ada", "repository": "ado", "status": "active", "isDraft": False},
    ]
    completed = [
        {"id": 21, "title": "4E report builder", "sourceRef": "claude/x", "targetRef": "dev",
         "createdBy": "Jason", "repository": "ado", "status": "completed", "isDraft": False},
        {"id": 22, "title": "Global search", "sourceRef": "claude/x", "targetRef": "dev",
         "createdBy": "Jason", "repository": "ado", "status": "active", "isDraft": False},
    ]

    async def fake_list(project, status="active", top=50):
        return active if status == "active" else completed

    monkeypatch.setattr(c, "list_pull_requests", fake_list)

    out = await c.search_pull_requests("Demo", "search")
    assert [p["id"] for p in out] == [22]  # matched once, deduped across statuses

    out = await c.search_pull_requests("Demo", "builder")
    assert [p["id"] for p in out] == [21]  # completed PRs searchable too

    out = await c.search_pull_requests("Demo", "!30")
    assert [p["id"] for p in out] == [30]  # !id lookup

    out = await c.search_pull_requests("Demo", "jason")
    assert {p["id"] for p in out} == {22, 21}  # author match, case-insensitive (30 is Ada's)


# ---- code index filters -------------------------------------------------------------


def test_indexable_skips_generated_and_binary():
    assert _indexable("/src/app/main.py")
    assert _indexable("/README.md")
    assert not _indexable("/frontend/node_modules/react/index.js")
    assert not _indexable("/logo.png")
    assert not _indexable("/frontend/package-lock.json")
    assert not _indexable("/a.lock")
    assert not _indexable("/dist/bundle.js")


def test_looks_minified():
    assert _looks_minified("var a=1;" * 5000)  # one huge line
    assert not _looks_minified("def f():\n    return 1\n" * 100)


# ---- code search over a fake client --------------------------------------------------


class FakeADO:
    def __init__(self):
        self.files = {
            "/src/app.py": "import os\n\ndef genie_ask():\n    return 'genie'\n",
            "/docs/notes.md": "Genie is the analytics tool.\n",
            "/src/other.py": "print('hello')\n",
        }

    async def list_repos(self, project):
        return [{"id": "r1", "name": "repo1", "defaultBranch": "main"}]

    async def list_branches(self, project, repo_id):
        return [{"name": "main"}, {"name": "dev"}]

    async def list_file_paths(self, project, repo_id, branch):
        self.indexed_branch = branch
        return list(self.files)

    async def get_files_bulk(self, project, repo_id, branch, paths, max_chars=0):
        return {p: self.files[p] for p in paths}


@pytest.mark.asyncio
async def test_code_search_matches_and_prefers_dev_branch():
    cs, fake = CodeSearch(), FakeADO()
    out = await cs.search("Demo", "genie", fake)
    assert out["available"] is True
    assert fake.indexed_branch == "dev"  # deploy trunk preferred over default
    paths = [r["path"] for r in out["results"]]
    assert "/src/app.py" in paths and "/docs/notes.md" in paths
    assert "/src/other.py" not in paths
    app_hit = next(r for r in out["results"] if r["path"] == "/src/app.py")
    assert {m["line"] for m in app_hit["matches"]} == {3, 4}  # case-insensitive


@pytest.mark.asyncio
async def test_code_search_caches_index():
    cs, fake = CodeSearch(), FakeADO()
    await cs.search("Demo", "genie", fake)
    fake.files["/new.py"] = "genie again\n"
    out = await cs.search("Demo", "genie", fake)  # within TTL — new file not seen
    assert all(r["path"] != "/new.py" for r in out["results"])


@pytest.mark.asyncio
async def test_code_search_reports_unavailable_on_index_failure():
    cs = CodeSearch()

    class Broken:
        async def list_repos(self, project):
            raise RuntimeError("ADO unreachable")

    out = await cs.search("Demo", "genie", Broken())
    assert out["available"] is False and "unreachable" in out["reason"]
