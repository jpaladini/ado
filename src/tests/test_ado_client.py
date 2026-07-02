"""Parsing tests for the ADO client, using a mock transport (no live ADO needed).

Run:  cd src && pip install -r requirements-dev.txt && pytest
"""
import httpx
import pytest

from app.ado.client import ADOClient

ROUTES = {
    ("POST", "/Demo/_apis/wit/wiql"): {"workItems": [{"id": 5}, {"id": 6}]},
    ("POST", "/_apis/wit/workitemsbatch"): {
        "value": [
            {
                "id": 5,
                "fields": {
                    "System.Title": "Fix login",
                    "System.State": "Active",
                    "System.WorkItemType": "Bug",
                    "System.AssignedTo": {"displayName": "Ada"},
                    "System.ChangedDate": "2026-06-20T00:00:00Z",
                },
            },
            {
                "id": 6,
                "fields": {
                    "System.Title": "Add export",
                    "System.State": "New",
                    "System.WorkItemType": "User Story",
                    "System.AssignedTo": None,
                },
            },
        ]
    },
    ("GET", "/Demo/_apis/git/pullrequests"): {
        "value": [
            {
                "pullRequestId": 12,
                "title": "Refactor",
                "status": "active",
                "isDraft": True,
                "createdBy": {"displayName": "Lin"},
                "repository": {"name": "core"},
                "sourceRefName": "refs/heads/feat",
                "targetRefName": "refs/heads/main",
            }
        ]
    },
    ("GET", "/Demo/_apis/build/builds"): {
        "value": [
            {
                "id": 99,
                "buildNumber": "20260628.1",
                "definition": {"name": "CI"},
                "status": "completed",
                "result": "succeeded",
                "requestedFor": {"displayName": "Bot"},
                "sourceBranch": "refs/heads/main",
            }
        ]
    },
    ("GET", "/Demo/_apis/git/repositories"): {
        "value": [{"id": "r1", "name": "core", "defaultBranch": "refs/heads/main"}]
    },
    ("GET", "/_apis/wit/workitems/7"): {
        "id": 7,
        "rev": 3,
        "fields": {
            "System.Title": "Fix login",
            "System.State": "Doing",
            "System.WorkItemType": "Task",
            "System.AssignedTo": {"displayName": "Ada", "uniqueName": "ada@example.com"},
            "System.Description": "<div>steps</div>",
            "System.Tags": "auth; p1",
            "System.IterationPath": "Demo\\Sprint 1",
            "System.AreaPath": "Demo",
            "System.CreatedBy": {"displayName": "Lin"},
            "System.CreatedDate": "2026-06-01T00:00:00Z",
            "System.ChangedDate": "2026-06-20T00:00:00Z",
        },
    },
    ("GET", "/Demo/_apis/wit/workitemtypes"): {
        "value": [
            {"name": "Task", "states": [{"name": "To Do", "category": "Proposed"}, {"name": "Doing", "category": "InProgress"}]},
            {"name": "Code Review Request", "states": [{"name": "Requested", "category": "Proposed"}]},
        ]
    },
    ("GET", "/Demo/_apis/wit/workitemtypecategories/Microsoft.HiddenCategory"): {
        "workItemTypes": [{"name": "Code Review Request"}]
    },
    ("GET", "/Demo/_apis/wit/classificationnodes/Iterations"): {
        "name": "Demo",
        "children": [
            {"name": "Sprint 1"},
            {"name": "Sprint 2", "children": [{"name": "Week 1"}]},
        ],
    },
    ("POST", "/_apis/IdentityPicker/Identities"): {
        "results": [
            {
                "identities": [
                    {"displayName": "Ada L", "mail": "ada@example.com", "active": True},
                    {"displayName": "No Mail", "mail": None, "samAccountName": None},
                ]
            }
        ]
    },
    ("GET", "/Demo/_apis/wit/workItems/7/comments"): {
        "comments": [
            {
                "id": 11,
                "text": "<div>looks good</div>",
                "format": "html",
                "createdBy": {"displayName": "Lin"},
                "createdDate": "2026-06-21T00:00:00Z",
            }
        ]
    },
    ("GET", "/Demo/_apis/git/repositories/r1/commits"): {
        "value": [
            {
                "commitId": "abcdef1234567890",
                "comment": "Initial",
                "author": {"name": "Ada", "date": "2026-06-01T00:00:00Z"},
            }
        ]
    },
}


def _handler(request: httpx.Request) -> httpx.Response:
    body = ROUTES.get((request.method, request.url.path))
    assert body is not None, f"unexpected {request.method} {request.url.path}"
    return httpx.Response(200, json=body)


@pytest.fixture
def client() -> ADOClient:
    c = ADOClient(org_url="https://dev.azure.com", pat="x")
    transport = httpx.MockTransport(_handler)
    c._client = lambda: httpx.AsyncClient(base_url=c.org_url, transport=transport)  # type: ignore[method-assign]
    return c


@pytest.mark.asyncio
async def test_work_items(client: ADOClient):
    wi = await client.list_work_items("Demo")
    assert wi[0]["title"] == "Fix login"
    assert wi[0]["assignedTo"] == "Ada"
    assert wi[1]["assignedTo"] is None  # null identity tolerated


@pytest.mark.asyncio
async def test_pull_requests(client: ADOClient):
    pr = (await client.list_pull_requests("Demo"))[0]
    assert pr["sourceRef"] == "feat" and pr["targetRef"] == "main"
    assert pr["isDraft"] is True and pr["repository"] == "core"


@pytest.mark.asyncio
async def test_builds(client: ADOClient):
    b = (await client.list_builds("Demo"))[0]
    assert b["result"] == "succeeded"
    assert b["sourceBranch"] == "main"


@pytest.mark.asyncio
async def test_repos_and_commits(client: ADOClient):
    repos = await client.list_repos("Demo")
    assert repos[0]["defaultBranch"] == "main"
    commits = await client.list_commits("Demo", "r1")
    assert commits[0]["shortId"] == "abcdef12"
    assert commits[0]["author"] == "Ada"


@pytest.mark.asyncio
async def test_work_item_detail(client: ADOClient):
    wi = await client.get_work_item(7)
    assert wi["title"] == "Fix login" and wi["state"] == "Doing"
    assert wi["assignedTo"] == "Ada" and wi["assignedToUnique"] == "ada@example.com"
    assert wi["tags"] == ["auth", "p1"]
    assert wi["iterationPath"] == "Demo\\Sprint 1"


@pytest.mark.asyncio
async def test_work_item_types_filters_hidden(client: ADOClient):
    types = await client.list_work_item_types("Demo")
    assert [t["name"] for t in types] == ["Task"]
    assert types[0]["states"][0] == {"name": "To Do", "category": "Proposed"}


@pytest.mark.asyncio
async def test_iterations_flatten(client: ADOClient):
    paths = await client.list_iterations("Demo")
    assert paths == ["Demo", "Demo\\Sprint 1", "Demo\\Sprint 2", "Demo\\Sprint 2\\Week 1"]


@pytest.mark.asyncio
async def test_identity_search(client: ADOClient):
    ids = await client.search_identities("ada")
    assert ids == [{"displayName": "Ada L", "uniqueName": "ada@example.com", "active": True}]
    # the mail-less identity is dropped (nothing to assign by)


@pytest.mark.asyncio
async def test_comments_list(client: ADOClient):
    comments = await client.list_work_item_comments("Demo", 7)
    assert comments[0]["text"] == "<div>looks good</div>"
    assert comments[0]["createdBy"] == "Lin"


# -- writes: assert the outgoing request is constructed correctly -------------


@pytest.fixture
def capturing():
    """Returns (client, captured_list). Each entry: (method, path, raw_path, headers, body)."""
    captured: list[tuple] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = req.content.decode() if req.content else ""
        captured.append((req.method, req.url.path, req.url.raw_path.decode(), dict(req.headers), body))
        if req.url.path.endswith("/connectionData"):
            return httpx.Response(200, json={"authenticatedUser": {"id": "user-123"}})
        return httpx.Response(200, json={"ok": True})

    c = ADOClient(org_url="https://dev.azure.com", pat="x")
    c._client = lambda: httpx.AsyncClient(base_url=c.org_url, transport=httpx.MockTransport(handler))  # type: ignore[method-assign]
    return c, captured


@pytest.mark.asyncio
async def test_update_work_item_uses_json_patch(capturing):
    import json

    client, cap = capturing
    await client.update_work_item(42, {"System.State": "Active"})
    method, path, _raw, headers, body = cap[-1]
    assert method == "PATCH" and path == "/_apis/wit/workitems/42"
    assert headers["content-type"] == "application/json-patch+json"
    assert json.loads(body) == [{"op": "add", "path": "/fields/System.State", "value": "Active"}]


@pytest.mark.asyncio
async def test_create_work_item_json_patch(capturing):
    import json

    client, cap = capturing
    await client.create_work_item(
        "Demo", "User Story", {"System.Title": "New", "System.Tags": "a; b"}
    )
    method, _path, raw, headers, body = cap[-1]
    assert method == "POST"
    assert "/Demo/_apis/wit/workitems/$User%20Story" in raw  # type is a $-prefixed segment
    assert headers["content-type"] == "application/json-patch+json"
    assert json.loads(body) == [
        {"op": "add", "path": "/fields/System.Title", "value": "New"},
        {"op": "add", "path": "/fields/System.Tags", "value": "a; b"},
    ]


@pytest.mark.asyncio
async def test_update_none_value_becomes_remove_op(capturing):
    import json

    client, cap = capturing
    await client.update_work_item(42, {"System.AssignedTo": None, "System.Title": "T"})
    _method, _path, _raw, _headers, body = cap[-1]
    assert json.loads(body) == [
        {"op": "remove", "path": "/fields/System.AssignedTo"},
        {"op": "add", "path": "/fields/System.Title", "value": "T"},
    ]


@pytest.mark.asyncio
async def test_add_comment_encodes_project(capturing):
    import json

    client, cap = capturing
    await client.add_work_item_comment("My Proj", 42, "looks good")
    method, _path, raw, _headers, body = cap[-1]
    assert method == "POST"
    assert "My%20Proj" in raw  # percent-encoded on the wire
    assert json.loads(body) == {"text": "looks good"}


@pytest.mark.asyncio
async def test_pr_vote_and_status(capturing):
    import json

    client, cap = capturing
    await client.set_pr_vote("Proj", "repo-1", 7, "user-123", 10)
    method, path, _raw, _headers, body = cap[-1]
    assert method == "PUT"
    assert path == "/Proj/_apis/git/repositories/repo-1/pullRequests/7/reviewers/user-123"
    assert json.loads(body) == {"vote": 10}

    await client.set_pr_status("Proj", "repo-1", 7, "abandoned")
    method, path, _raw, _headers, body = cap[-1]
    assert method == "PATCH"
    assert path == "/Proj/_apis/git/repositories/repo-1/pullRequests/7"
    assert json.loads(body) == {"status": "abandoned"}
