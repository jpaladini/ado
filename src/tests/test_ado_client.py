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
    ("GET", "/Demo/_apis/build/builds/99/timeline"): {
        "records": [
            {"id": "t1", "parentId": "j1", "type": "Task", "name": "pytest", "state": "completed",
             "result": "failed", "order": 2, "errorCount": 1, "log": {"id": 5},
             "issues": [{"type": "error", "message": "1 test failed"}, {"type": "warning"}]},
            {"id": "s1", "parentId": None, "type": "Stage", "name": "Build", "state": "completed",
             "result": "failed", "order": 1},
            {"id": "t0", "parentId": "j1", "type": "Task", "name": "checkout", "state": "completed",
             "result": "succeeded", "order": 1, "log": {"id": 4}},
        ]
    },
    ("GET", "/Demo/_apis/build/builds/99/logs/5"): lambda req: httpx.Response(
        200, text="collecting tests\n##[error]assert 1 == 2\n"
    ),
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
    ("GET", "/Demo/_apis/git/repositories/r1/refs"): {
        "value": [
            {"name": "refs/heads/main", "objectId": "aaa111"},
            {"name": "refs/heads/dev", "objectId": "bbb222"},
        ]
    },
    ("GET", "/Demo/_apis/git/repositories/r1/items"): lambda req: _items_handler(req),
    ("GET", "/Demo/_apis/git/repositories/r1/pullRequests/12"): {
        "pullRequestId": 12,
        "title": "Refactor",
        "status": "active",
        "sourceRefName": "refs/heads/feat",
        "targetRefName": "refs/heads/main",
        "lastMergeSourceCommit": {"commitId": "headcommit"},
        "lastMergeTargetCommit": {"commitId": "basecommit"},
    },
    ("GET", "/Demo/_apis/git/repositories/r1/pullRequests/12/iterations"): {
        "value": [
            {"id": 1, "sourceRefCommit": {"commitId": "old"}, "targetRefCommit": {"commitId": "older"}},
            {"id": 2, "sourceRefCommit": {"commitId": "headcommit"}, "targetRefCommit": {"commitId": "basecommit"}},
        ]
    },
    ("GET", "/Demo/_apis/git/repositories/r1/pullRequests/12/iterations/2/changes"): {
        "changeEntries": [
            {"changeType": "edit", "item": {"path": "/src/app.py", "gitObjectType": "blob"}},
            {"changeType": "rename", "originalPath": "/old.md", "item": {"path": "/new.md", "gitObjectType": "blob"}},
            {"changeType": "edit", "item": {"path": "/src", "gitObjectType": "tree"}},
            {"changeType": "add", "item": {"path": "/added.txt", "gitObjectType": "blob"}},
            {"changeType": "edit", "item": {"path": "/logo.png", "gitObjectType": "blob"}},
        ]
    },
    ("GET", "/Demo/_apis/git/repositories/r1/pullRequests/12/threads"): {
        "value": [
            {"id": 1, "comments": [{"id": 1, "commentType": "system", "content": "joined"}]},
            {
                "id": 2,
                "status": "active",
                "threadContext": {"filePath": "/src/app.py", "rightFileStart": {"line": 7, "offset": 1}},
                "comments": [
                    {"id": 10, "commentType": "text", "content": "nit: rename this",
                     "author": {"displayName": "Lin"}, "publishedDate": "2026-07-01T00:00:00Z"},
                    {"id": 11, "commentType": "text", "content": "deleted one", "isDeleted": True},
                ],
            },
            {"id": 3, "isDeleted": True, "comments": [{"commentType": "text", "content": "gone"}]},
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


def _items_handler(req: httpx.Request):
    """/items serves both trees (recursionLevel) and file content (includeContent),
    keyed further by version for PR diff sides."""
    p = req.url.params
    if p.get("recursionLevel"):
        scope = p.get("scopePath") or "/"
        return {
            "value": [
                {"path": scope, "isFolder": True},  # self-echo, must be dropped
                {"path": f"{scope.rstrip('/')}/zebra.py", "gitObjectType": "blob", "size": 10},
                {"path": f"{scope.rstrip('/')}/alpha", "isFolder": True, "gitObjectType": "tree"},
                {"path": f"{scope.rstrip('/')}/beta.md", "gitObjectType": "blob", "size": 5},
            ]
        }
    version = p.get("versionDescriptor.version")
    path = p.get("path")
    if path == "/logo.png":
        return {"path": path, "objectId": "bin1"}  # no content key → binary
    if path == "/added.txt" and version == "basecommit":
        return httpx.Response(404, json={"message": "not found"})
    if version == "basecommit":
        return {"path": path, "content": "line1\nline2\n", "objectId": "o1", "commitId": version}
    return {"path": path, "content": "line1\nline2 changed\nline3\n", "objectId": "o2", "commitId": version}


def _handler(request: httpx.Request) -> httpx.Response:
    body = ROUTES.get((request.method, request.url.path))
    assert body is not None, f"unexpected {request.method} {request.url.path}"
    if callable(body):  # param-dependent payloads (e.g. /items tree vs file) or 404s
        body = body(request)
    if isinstance(body, httpx.Response):
        return body
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
async def test_build_timeline(client: ADOClient):
    recs = await client.get_build_timeline("Demo", 99)
    assert [r["name"] for r in recs] == ["Build", "checkout", "pytest"]  # order-sorted
    task = recs[-1]
    assert task["logId"] == 5 and task["errorCount"] == 1
    # message-less issues are dropped
    assert task["issues"] == [{"type": "error", "message": "1 test failed"}]
    assert recs[0]["logId"] is None


@pytest.mark.asyncio
async def test_build_log_keeps_tail_when_truncating(client: ADOClient):
    log = await client.get_build_log("Demo", 99, 5)
    assert log["truncated"] is False and "##[error]assert 1 == 2" in log["content"]
    tail = await client.get_build_log("Demo", 99, 5, max_chars=20)
    assert tail["truncated"] is True
    assert tail["content"] == log["content"][-20:]  # tail, not head


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


# -- code browsing & PR review -------------------------------------------------


def test_unified_diff_pure():
    from app.ado.client import unified_diff

    edit = unified_diff("a\nb\nc", "a\nB\nc", "/f.py")
    assert edit["addedLines"] == 1 and edit["removedLines"] == 1
    assert "+B" in edit["diff"] and "-b" in edit["diff"] and "a/f.py" in edit["diff"]

    add = unified_diff(None, "x\ny", "/new.txt")
    assert add["addedLines"] == 2 and add["removedLines"] == 0

    delete = unified_diff("x\ny", None, "/gone.txt")
    assert delete["removedLines"] == 2 and delete["addedLines"] == 0

    same = unified_diff("x", "x", "/same.txt")
    assert same["diff"] == "" and same["addedLines"] == 0


@pytest.mark.asyncio
async def test_branches(client: ADOClient):
    branches = await client.list_branches("Demo", "r1")
    assert branches == [
        {"name": "main", "objectId": "aaa111"},
        {"name": "dev", "objectId": "bbb222"},
    ]


@pytest.mark.asyncio
async def test_tree_drops_self_and_sorts_folders_first(client: ADOClient):
    tree = await client.get_tree("Demo", "r1", "main", "/src")
    assert [e["name"] for e in tree] == ["alpha", "beta.md", "zebra.py"]
    assert tree[0]["isFolder"] is True and tree[1]["isFolder"] is False


@pytest.mark.asyncio
async def test_get_file_text_and_binary(client: ADOClient):
    f = await client.get_file("Demo", "r1", "/src/app.py")
    assert f["binary"] is False and "line1" in f["content"]
    b = await client.get_file("Demo", "r1", "/logo.png")
    assert b["binary"] is True and b["content"] == ""


@pytest.mark.asyncio
async def test_pr_files_latest_iteration(client: ADOClient):
    info = await client.pr_files("Demo", "r1", 12)
    assert info["iteration"] == 2  # latest wins
    assert info["sourceCommit"] == "headcommit" and info["targetCommit"] == "basecommit"
    paths = [f["path"] for f in info["files"]]
    assert "/src" not in paths  # tree entries dropped
    rename = next(f for f in info["files"] if f["changeType"] == "rename")
    assert rename["originalPath"] == "/old.md" and rename["path"] == "/new.md"


@pytest.mark.asyncio
async def test_pr_file_diff_edit_add_binary(client: ADOClient):
    edit = await client.pr_file_diff("Demo", "r1", 12, "/src/app.py")
    assert edit["binary"] is False and edit["addedLines"] >= 1 and "-line2" in edit["diff"]

    added = await client.pr_file_diff("Demo", "r1", 12, "/added.txt")  # base side 404s
    assert added["removedLines"] == 0 and added["addedLines"] >= 1

    binary = await client.pr_file_diff("Demo", "r1", 12, "/logo.png")
    assert binary["binary"] is True and binary["diff"] == ""


@pytest.mark.asyncio
async def test_pr_threads_filtering(client: ADOClient):
    threads = await client.list_pr_threads("Demo", "r1", 12)
    assert len(threads) == 1  # system-only + deleted threads dropped
    t = threads[0]
    assert t["filePath"] == "/src/app.py" and t["line"] == 7
    assert [c["content"] for c in t["comments"]] == ["nit: rename this"]
    assert t["comments"][0]["author"] == "Lin"


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
async def test_create_pr_thread_requests(capturing):
    import json

    client, cap = capturing
    # general comment: no threadContext
    await client.create_pr_thread("Proj", "r1", 7, "looks good overall")
    method, path, _raw, _headers, body = cap[-1]
    assert method == "POST" and path.endswith("/pullRequests/7/threads")
    sent = json.loads(body)
    assert sent["comments"] == [{"parentCommentId": 0, "content": "looks good overall", "commentType": 1}]
    assert "threadContext" not in sent

    # file-anchored: threadContext + leading-slash normalization
    await client.create_pr_thread("Proj", "r1", 7, "nit", file_path="src/x.py", line=42)
    sent = json.loads(cap[-1][4])
    assert sent["threadContext"]["filePath"] == "/src/x.py"
    assert sent["threadContext"]["rightFileStart"] == {"line": 42, "offset": 1}
    assert sent["threadContext"]["rightFileEnd"] == {"line": 42, "offset": 1}


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


@pytest.mark.asyncio
async def test_connection_data_sends_no_api_version():
    """connectionData is unversioned — api-version=7.1 gets a 400 from ADO,
    which broke PR approve (reviewer id resolves through here)."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"authenticatedUser": {"id": "u1", "providerDisplayName": "Jason"}})

    c = ADOClient(org_url="https://dev.azure.com/myorg", pat="x")
    transport = httpx.MockTransport(handler)
    c._client = lambda: httpx.AsyncClient(base_url=c.org_url, transport=transport)  # type: ignore[method-assign]
    me = await c.connection_data()
    assert me == {"id": "u1", "displayName": "Jason"}
    assert "api-version" not in seen["params"]


@pytest.mark.asyncio
async def test_push_branch_with_edits_resolves_change_types():
    """Existing file → 'edit', missing file → 'add'; branch created off base sha."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/refs"):
            return httpx.Response(200, json={"value": [
                {"name": "refs/heads/dev", "objectId": "abc123"}]})
        if path.endswith("/items"):
            # /exists.py is present on the branch; /new.py is not
            if request.url.params.get("path") == "/exists.py":
                return httpx.Response(200, json={"path": "/exists.py"})
            return httpx.Response(404, json={})
        if path.endswith("/pushes"):
            import json as _json
            captured["push"] = _json.loads(request.content)
            return httpx.Response(201, json={"pushId": 9})
        raise AssertionError(f"unexpected {path}")

    c = ADOClient(org_url="https://dev.azure.com/myorg", pat="x")
    c._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url=c.org_url, transport=httpx.MockTransport(handler))

    out = await c.push_branch_with_edits(
        "Demo", "r1", "dev", "copilot/fix-1", "fix things",
        [{"path": "/exists.py", "content": "new"}, {"path": "/new.py", "content": "brand new"}],
    )
    assert out == {"pushId": 9}
    push = captured["push"]
    assert push["refUpdates"] == [{"name": "refs/heads/copilot/fix-1", "oldObjectId": "abc123"}]
    changes = push["commits"][0]["changes"]
    assert {c["item"]["path"]: c["changeType"] for c in changes} == {
        "/exists.py": "edit", "/new.py": "add"}


@pytest.mark.asyncio
async def test_push_branch_with_edits_missing_base_branch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    c = ADOClient(org_url="https://dev.azure.com/myorg", pat="x")
    c._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url=c.org_url, transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="base branch 'ghost' not found"):
        await c.push_branch_with_edits("Demo", "r1", "ghost", "b", "m",
                                       [{"path": "/a", "content": "x"}])


@pytest.mark.asyncio
async def test_list_pull_requests_computes_ado_approval():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [
            {"pullRequestId": 1, "title": "a", "status": "active", "mergeStatus": "succeeded",
             "reviewers": [{"vote": 10}, {"vote": 0}]},
            {"pullRequestId": 2, "title": "b", "status": "active", "mergeStatus": "succeeded",
             "reviewers": [{"vote": 10}, {"vote": -5}]},  # someone is waiting → not approved
            {"pullRequestId": 3, "title": "c", "status": "active", "mergeStatus": "conflicts",
             "reviewers": []},  # nobody voted → not approved
        ]})

    c = ADOClient(org_url="https://dev.azure.com/myorg", pat="x")
    c._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url=c.org_url, transport=httpx.MockTransport(handler))
    prs = await c.list_pull_requests("Demo")
    assert [p["isApproved"] for p in prs] == [True, False, False]
    assert prs[2]["mergeStatus"] == "conflicts"
