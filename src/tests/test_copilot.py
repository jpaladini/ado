"""Agent-loop tests: scripted endpoint responses, no workspace or ADO needed."""
import json

import httpx
import pytest

from app import copilot


def _mk_response(content=None, tool_calls=None):
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}]}


def _tc(call_id, name, args):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(copilot, "resolve_endpoint", lambda: "fake-endpoint")
    monkeypatch.setattr(copilot, "_mlflow", lambda: None)  # tracing off in tests


@pytest.mark.asyncio
async def test_write_tool_becomes_proposal_not_execution(monkeypatch):
    """A create call is recorded as a proposal; nothing hits ADO."""
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "create_work_item", {"type": "Task", "title": "Fix login"})]),
        _mk_response(content="Proposed a Task 'Fix login' — apply it to create."),
    ])
    sent = []

    async def fake_invoke(endpoint, messages, tools):
        sent.append(list(messages))
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)

    out = await copilot.chat("home", "make a task to fix login")
    assert out["proposals"] == [
        {"id": "p1", "tool": "create_work_item", "args": {"type": "Task", "title": "Fix login"}}
    ]
    assert out["toolCalls"] == []  # write tools are not "made" calls
    assert "apply" in out["reply"].lower()
    # the model saw a tool result saying the proposal was recorded
    tool_msg = sent[1][-1]
    assert tool_msg["role"] == "tool" and "Recorded" in tool_msg["content"]


@pytest.mark.asyncio
async def test_read_tool_executes_and_feeds_back(monkeypatch):
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "list_work_items", {"top": 5})]),
        _mk_response(content="You have 2 items."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    async def fake_read(name, args, project):
        assert name == "list_work_items" and project == "home"
        return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "_run_read_tool", fake_read)

    out = await copilot.chat("home", "what's open?")
    assert out["toolCalls"] == [{"name": "list_work_items", "args": {"top": 5}}]
    assert out["proposals"] == []
    assert out["reply"] == "You have 2 items."


@pytest.mark.asyncio
async def test_read_tool_error_is_reported_not_raised(monkeypatch):
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "get_work_item", {"id": 999})]),
        _mk_response(content="Item 999 doesn't seem to exist."),
    ])
    sent = []

    async def fake_invoke(endpoint, messages, tools):
        sent.append(list(messages))
        return next(responses)

    async def fake_read(name, args, project):
        raise RuntimeError("404 from ADO")

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "_run_read_tool", fake_read)

    out = await copilot.chat("home", "show item 999")
    assert "doesn't seem to exist" in out["reply"]
    assert "RuntimeError" in sent[1][-1]["content"]  # error surfaced to the model


@pytest.mark.asyncio
async def test_history_and_reasoning_content_blocks(monkeypatch):
    """History lands in messages; list-of-blocks content (reasoning models) parses."""
    captured = {}

    async def fake_invoke(endpoint, messages, tools):
        captured["messages"] = list(messages)
        return _mk_response(content=[
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hmm"}]},
            {"type": "text", "text": "Final answer."},
        ])

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    out = await copilot.chat("home", "hi", history=[
        {"role": "user", "content": "earlier q"},
        {"role": "assistant", "content": "earlier a"},
    ])
    assert out["reply"] == "Final answer."
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def _http404(url: str) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", url)
    return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))


class _FakeADO:
    """get_work_item / get_pull_request 404 for id 999, succeed otherwise."""

    def __init__(self, *a, **k):
        pass

    async def get_work_item(self, wid):
        if wid == 999:
            raise _http404("https://ado/_apis/wit/workitems/999")
        return {"id": wid, "title": "exists"}

    async def get_pull_request(self, project, repo_id, pr_id):
        if pr_id == 999:
            raise _http404("https://ado/_apis/git/pullRequests/999")
        return {"id": pr_id, "title": "a pr", "status": "active"}


@pytest.mark.asyncio
async def test_update_proposal_against_missing_item_is_rejected(monkeypatch):
    """A guessed ID never becomes a proposal; the model gets told to look first."""
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "update_work_item", {"id": 999, "tags": "new"})]),
        _mk_response(content="Item 999 doesn't exist — let me check the list."),
    ])
    sent = []

    async def fake_invoke(endpoint, messages, tools):
        sent.append(list(messages))
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", _FakeADO)

    out = await copilot.chat("home", "tag item 999")
    assert out["proposals"] == []  # rejected, never surfaced to the user
    assert "does not exist" in sent[1][-1]["content"]
    assert "Do not guess IDs" in sent[1][-1]["content"]


@pytest.mark.asyncio
async def test_update_proposal_against_real_item_passes_verification(monkeypatch):
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "update_work_item", {"id": 4, "tags": "new"})]),
        _mk_response(content="Proposed."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", _FakeADO)

    out = await copilot.chat("home", "tag item 4")
    assert out["proposals"] == [{"id": "p1", "tool": "update_work_item", "args": {"id": 4, "tags": "new"}}]


@pytest.mark.asyncio
async def test_create_proposal_skips_verification(monkeypatch):
    """create_work_item has no target id — must not touch ADO at all."""
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "create_work_item", {"type": "Task", "title": "New"})]),
        _mk_response(content="Proposed."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    class ExplodingADO:
        def __init__(self, *a, **k):
            raise AssertionError("ADO must not be constructed for create proposals")

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", ExplodingADO)

    out = await copilot.chat("home", "make a task")
    assert len(out["proposals"]) == 1


@pytest.mark.asyncio
async def test_pr_comment_proposal_verified(monkeypatch):
    """A comment on a real PR becomes a proposal; PR 999 or missing repositoryId is rejected."""
    responses = iter([
        _mk_response(tool_calls=[
            _tc("c1", "comment_on_pr_file", {"prId": 12, "repositoryId": "r1", "path": "/src/app.py", "line": 7, "comment": "nit"}),
            _tc("c2", "comment_on_pr", {"prId": 999, "repositoryId": "r1", "comment": "hello"}),
            _tc("c3", "comment_on_pr", {"prId": 12, "comment": "no repo id"}),
        ]),
        _mk_response(content="Proposed one comment; the other targets were invalid."),
    ])
    sent = []

    async def fake_invoke(endpoint, messages, tools):
        sent.append(list(messages))
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", _FakeADO)

    out = await copilot.chat("home", "review pr 12")
    assert out["proposals"] == [{
        "id": "p1",
        "tool": "comment_on_pr_file",
        "args": {"prId": 12, "repositoryId": "r1", "path": "/src/app.py", "line": 7, "comment": "nit"},
    }]
    fed_back = "".join(m["content"] for m in sent[1] if m["role"] == "tool")
    assert "does not exist" in fed_back  # PR 999
    assert "look them up first" in fed_back  # missing repositoryId


def test_truncate_diff():
    short = {"diff": "+a\n-b", "addedLines": 1, "removedLines": 1}
    assert copilot._truncate_diff(short) == short  # untouched

    long = {"diff": "\n".join(f"+line {i}" for i in range(1000))}
    cut = copilot._truncate_diff(long)
    kept = cut["diff"].split("\n")
    assert len(kept) <= copilot.DIFF_LINE_LIMIT
    assert len(cut["diff"]) <= copilot.DIFF_CHAR_LIMIT
    assert "truncated" in cut["truncatedNote"]
    assert kept[-1].startswith("+line")  # cut on a line boundary


def test_window_file():
    f = {"path": "/x.py", "binary": False, "content": "\n".join(str(i) for i in range(1, 501))}
    default = copilot._window_file(f, None, None)
    assert default["lines"] == f"1-{copilot.FILE_LINE_LIMIT}" and default["totalLines"] == 500
    window = copilot._window_file(f, 250, 260)
    assert window["content"].split("\n") == [str(i) for i in range(250, 261)]


@pytest.mark.asyncio
async def test_text_form_pr_comment_lifted(monkeypatch):
    """_TOOL_NAME_ALT picked up the new tool names for the llama text fallback."""
    responses = iter([
        _mk_response(content='comment_on_pr(prId=12, repositoryId="r1", comment="nit")\n\nDone.'),
        _mk_response(content="Proposed."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", _FakeADO)

    out = await copilot.chat("home", "comment on pr 12")
    assert out["proposals"] == [{
        "id": "p1", "tool": "comment_on_pr",
        "args": {"prId": 12, "repositoryId": "r1", "comment": "nit"},
    }]


@pytest.mark.asyncio
async def test_genie_history_tool(monkeypatch):
    """query_analytics_history routes through genie.ask and truncates rows."""
    async def fake_ask(question, conversation_id=None):
        assert question == "open items trend"
        return {"text": ["Trend is flat."], "queryDescription": "desc",
                "columns": ["d", "n"], "rows": [["2026-07-01", "1"]] * 80}

    monkeypatch.setattr("app.copilot.genie.ask", fake_ask)
    out = await copilot._run_read_tool("query_analytics_history", {"question": "open items trend"}, "home")
    assert out["text"] == "Trend is flat."
    assert len(out["rows"]) == 50
    assert "not real-time" in out["note"]


@pytest.mark.asyncio
async def test_genie_history_tool_unconfigured(monkeypatch):
    from app import genie as genie_mod

    async def fake_ask(question, conversation_id=None):
        raise genie_mod.GenieNotConfigured("no space set")

    monkeypatch.setattr("app.copilot.genie.ask", fake_ask)
    out = await copilot._run_read_tool("query_analytics_history", {"question": "x"}, "home")
    assert out == {"error": "no space set"}


def test_parse_text_tool_calls():
    """The llama text-form call + 'assistant' artifact gets lifted and stripped."""
    text = 'update_work_item(id=2, tags="triage")assistant\n\nProposed updates to both items.'
    cleaned, calls = copilot._parse_text_tool_calls(text)
    assert cleaned == "Proposed updates to both items."
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "update_work_item"
    assert json.loads(calls[0]["function"]["arguments"]) == {"id": 2, "tags": "triage"}


def test_parse_text_tool_calls_leaves_prose_alone():
    text = "You should update work item 4 (it needs tags)."
    cleaned, calls = copilot._parse_text_tool_calls(text)
    assert cleaned == text and calls == []


@pytest.mark.asyncio
async def test_text_form_call_becomes_proposal(monkeypatch):
    """A message with no structured tool_calls but a text-form write call still
    yields a proposal, and the loop continues to a real final answer."""
    responses = iter([
        _mk_response(content='update_work_item(id=4, tags="triage")assistant\n\nDone.'),
        _mk_response(content="Proposed the tag update; awaiting your approval."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "ADOClient", _FakeADO)

    out = await copilot.chat("home", "tag item 4")
    assert out["proposals"] == [{"id": "p1", "tool": "update_work_item", "args": {"id": 4, "tags": "triage"}}]
    assert out["reply"] == "Proposed the tag update; awaiting your approval."


@pytest.mark.asyncio
async def test_step_limit(monkeypatch):
    async def always_tool_call(endpoint, messages, tools):
        return _mk_response(tool_calls=[_tc("x", "list_work_items", {})])

    async def fake_read(name, args, project):
        return []

    monkeypatch.setattr(copilot, "_invoke", always_tool_call)
    monkeypatch.setattr(copilot, "_run_read_tool", fake_read)

    out = await copilot.chat("home", "loop forever")
    assert "step limit" in out["reply"]
    assert len(out["toolCalls"]) == copilot.MAX_TURNS


@pytest.mark.asyncio
async def test_genie_tables_surface_as_artifacts(monkeypatch):
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "query_analytics_history", {"question": "items by state"})]),
        _mk_response(content="Mostly To Do."),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    async def fake_read(name, args, project):
        return {"text": "…", "columns": ["state", "n"], "rows": [["To Do", 3]], "note": "batch"}

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "_run_read_tool", fake_read)

    out = await copilot.chat("home", "items by state?")
    assert out["tables"] == [{"name": "items by state", "columns": ["state", "n"], "rows": [["To Do", 3]]}]


@pytest.mark.asyncio
async def test_non_tabular_tool_results_produce_no_tables(monkeypatch):
    responses = iter([
        _mk_response(tool_calls=[_tc("c1", "list_work_items", {})]),
        _mk_response(content="done"),
    ])

    async def fake_invoke(endpoint, messages, tools):
        return next(responses)

    async def fake_read(name, args, project):
        return [{"id": 1}]

    monkeypatch.setattr(copilot, "_invoke", fake_invoke)
    monkeypatch.setattr(copilot, "_run_read_tool", fake_read)

    out = await copilot.chat("home", "list items")
    assert out["tables"] == []


# ---- _run_read_tool dispatch (fake clients, every branch) ---------------------------


class _ReadFakeADO:
    def __init__(self):
        self.calls = []

    def _rec(self, name, *a, **kw):
        self.calls.append((name, a, kw))

    async def pr_files(self, *a, **kw):
        self._rec("pr_files", *a); return {"files": []}

    async def pr_file_diff(self, *a, **kw):
        self._rec("pr_file_diff", *a); return {"diff": "x" * 10, "addedLines": 1, "removedLines": 0}

    async def list_pr_threads(self, *a, **kw):
        self._rec("list_pr_threads", *a); return []

    async def list_repos(self, *a, **kw):
        self._rec("list_repos", *a)
        return [{"id": "r1", "name": "ado", "defaultBranch": "dev"}]

    async def get_file(self, *a, **kw):
        self._rec("get_file", *a, **kw)
        return {"path": "/f.py", "binary": False, "truncated": False,
                "content": "\n".join(f"line{i}" for i in range(1, 21))}

    async def list_work_items(self, *a, **kw):
        self._rec("list_work_items", *a, **kw); return [{"id": 1}]

    async def get_work_item(self, *a, **kw):
        self._rec("get_work_item", *a); return {"id": a[0]}

    async def list_work_item_comments(self, *a, **kw):
        self._rec("comments", *a); return []

    async def search_identities(self, *a, **kw):
        self._rec("identities", *a); return []

    async def list_pull_requests(self, *a, **kw):
        self._rec("list_prs", *a, **kw); return []

    async def list_builds(self, *a, **kw):
        self._rec("builds", *a, **kw); return []


@pytest.fixture
def fake_ado(monkeypatch):
    fake = _ReadFakeADO()
    monkeypatch.setattr(copilot, "ADOClient", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_read_tool_dispatch_covers_ado_tools(fake_ado):
    r = await copilot._run_read_tool("list_work_items", {"top": 999}, "home")
    assert r == [{"id": 1}]
    assert fake_ado.calls[-1][2]["top"] == 200  # clamped

    r = await copilot._run_read_tool("get_work_item", {"id": "7"}, "home")
    assert r == {"id": 7}

    await copilot._run_read_tool("list_pull_requests", {}, "home")
    assert fake_ado.calls[-1][2]["status"] == "active"

    await copilot._run_read_tool("list_builds", {}, "home")
    await copilot._run_read_tool("list_work_item_comments", {"id": 3}, "home")
    await copilot._run_read_tool("search_identities", {"query": "ja"}, "home")
    await copilot._run_read_tool("list_pr_threads", {"repositoryId": "r1", "prId": 4}, "home")
    await copilot._run_read_tool("list_pr_files", {"repositoryId": "r1", "prId": 4}, "home")
    d = await copilot._run_read_tool("get_pr_file_diff",
                                     {"repositoryId": "r1", "prId": 4, "path": "/f"}, "home")
    assert "diff" in d

    with pytest.raises(ValueError):
        await copilot._run_read_tool("nope", {}, "home")


@pytest.mark.asyncio
async def test_get_file_resolves_default_branch_and_windows(fake_ado):
    out = await copilot._run_read_tool(
        "get_file", {"repositoryId": "ado", "path": "/f.py", "startLine": 5, "endLine": 7}, "home"
    )
    # branch was resolved from list_repos (dev), and the window is honored
    assert any(c[0] == "list_repos" for c in fake_ado.calls)
    assert out["lines"] == "5-7" and out["content"] == "line5\nline6\nline7"


@pytest.mark.asyncio
async def test_get_flow_metrics_business_days_and_percentiles(monkeypatch):
    class _FakeAnalytics:
        async def created_per_day(self, *a, **kw):
            return [{"dateSK": 20260701, "count": 2}]

        async def completed_per_day(self, *a, **kw):
            return [{"dateSK": 20260702, "count": 1}]

        async def cycle_time_items(self, *a, **kw):
            return [{"id": 1, "title": "t", "type": "Issue", "cycleBdays": 2,
                     "leadBdays": 3, "closedDate": "2026-07-02"}]

        async def open_items_detail(self, *a, **kw):
            return [{"id": 2, "title": "o", "type": "Issue", "state": "Doing",
                     "category": "InProgress", "assignee": None,
                     "ageBdays": 4, "ageDays": 6}]

    monkeypatch.setattr(copilot, "AnalyticsClient", _FakeAnalytics)
    out = await copilot._run_read_tool("get_flow_metrics", {"days": 300}, "home")
    assert out["windowDays"] == 90  # clamped from 300
    assert out["cycleTimeP50BusinessDays"] == 2
    assert out["workloadByAssignee"] == {"Unassigned": 1}
    assert out["oldestOpenItems"][0]["ageBusinessDays"] == 4
    assert "business days" in out["note"]
