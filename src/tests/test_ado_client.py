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
