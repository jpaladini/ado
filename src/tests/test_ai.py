"""Suggestion-parsing tests for app.ai — fake endpoint, no workspace needed."""
import json

import pytest

from app import ai, copilot


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(ai, "resolve_endpoint", lambda: "fake-endpoint")
    monkeypatch.setattr(ai, "_span", lambda name, **a: __import__("contextlib").nullcontext(None))


def _fake_invoke(msg, capture=None):
    async def fake(endpoint, messages, tools, **kwargs):
        if capture is not None:
            capture.update({"messages": messages, "tools": tools, **kwargs})
        return {"choices": [{"message": msg}]}

    return fake


@pytest.mark.asyncio
async def test_structured_tool_call(monkeypatch):
    captured: dict = {}
    msg = {
        "tool_calls": [{
            "function": {
                "name": "suggest_work_item",
                "arguments": json.dumps({
                    "title": "  Fix login flow  ",
                    "description": "Users hit a blank page.",
                    "tags": "auth, p1;  ux ",
                    "acceptanceCriteria": "- login works",
                    "type": "",
                }),
            }
        }]
    }
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg, captured))

    out = await ai.suggest_work_item("home", {"title": "login broken"})
    s = out["suggestion"]
    assert s["title"] == "Fix login flow"
    assert s["tags"] == "auth; p1; ux"  # normalized separators
    assert "type" not in s  # empty fields dropped
    assert out["endpoint"] == "fake-endpoint"
    # forced tool choice + low temperature landed in the call
    assert captured["tool_choice"]["function"]["name"] == "suggest_work_item"
    assert captured["temperature"] == 0.2


@pytest.mark.asyncio
async def test_text_form_call_parsed(monkeypatch):
    msg = {"content": 'suggest_work_item(title="New title", description="Body", tags="a; b")'}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))
    out = await ai.suggest_work_item("home", {"description": "rough draft"})
    assert out["suggestion"]["title"] == "New title"


@pytest.mark.asyncio
async def test_bare_json_content_parsed(monkeypatch):
    msg = {"content": json.dumps({"title": "T", "description": "D", "tags": "x"})}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))
    out = await ai.suggest_work_item("home", {"title": "t"})
    assert out["suggestion"] == {"title": "T", "description": "D", "tags": "x"}


@pytest.mark.asyncio
async def test_prose_only_raises(monkeypatch):
    msg = {"content": "I think this work item is about login problems."}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))
    with pytest.raises(ai.SuggestionParseError):
        await ai.suggest_work_item("home", {"title": "t"})


# -- PR review ---------------------------------------------------------------------

DIFF = (
    "--- a/src/x.py\n"
    "+++ b/src/x.py\n"
    "@@ -1,3 +1,4 @@\n"
    " keep\n"
    "+added line 2\n"
    " keep\n"
    "+added line 4\n"
    "@@ -10,2 +11,3 @@\n"
    " keep\n"
    "+added line 12\n"
    " keep\n"
)


def test_right_side_lines_multi_hunk():
    assert ai.right_side_lines(DIFF) == {2, 4, 12}


def test_validate_comments_clamps_and_drops():
    lines = {"/src/x.py": {2, 4, 12}}
    raw = [
        {"path": "/src/x.py", "line": 4, "comment": "exact", "severity": "issue"},
        {"path": "src/x.py", "line": 99, "comment": "clamped + slash-normalized", "severity": "weird"},
        {"path": "/other.py", "line": 1, "comment": "unknown file", "severity": "nit"},
        {"path": "/src/x.py", "line": 2, "comment": "", "severity": "nit"},
    ]
    valid, dropped = ai._validate_comments(raw, lines)
    assert dropped == 2  # unknown file + empty comment
    assert valid[0] == {"path": "/src/x.py", "line": 4, "comment": "exact", "severity": "issue"}
    assert valid[1]["line"] == 12  # 99 clamped to nearest changed line
    assert valid[1]["severity"] == "suggestion"  # invalid severity normalized


class _ReviewADO:
    def __init__(self, *a, **k):
        pass

    async def pr_files(self, project, repo_id, pr_id):
        return {
            "iteration": 2,
            "sourceCommit": "s",
            "targetCommit": "t",
            "files": [
                {"path": "/src/x.py", "originalPath": None, "changeType": "edit"},
                {"path": "/logo.png", "originalPath": None, "changeType": "edit"},
            ],
        }

    async def pr_file_diff(self, project, repo_id, pr_id, path):
        if path == "/logo.png":
            return {"path": path, "binary": True, "diff": "", "addedLines": 0, "removedLines": 0}
        return {"path": path, "binary": False, "diff": DIFF, "addedLines": 3, "removedLines": 0}


@pytest.mark.asyncio
async def test_review_pr_end_to_end(monkeypatch):
    monkeypatch.setattr(ai, "ADOClient", _ReviewADO)
    msg = {
        "tool_calls": [{
            "function": {
                "name": "suggest_review_comments",
                "arguments": json.dumps({
                    "summary": "Small change, one concern.",
                    "comments": [
                        {"path": "/src/x.py", "line": 999, "comment": "check bounds", "severity": "issue"},
                    ],
                }),
            }
        }]
    }
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))

    out = await ai.review_pr("home", "r1", 12)
    assert out["filesReviewed"] == 1
    assert out["skipped"] == ["/logo.png"]  # binary skipped
    assert out["comments"][0]["line"] in {2, 4, 12}  # 999 clamped
    assert out["summary"] == "Small change, one concern."


@pytest.mark.asyncio
async def test_review_pr_path_filter(monkeypatch):
    calls = []

    class TrackingADO(_ReviewADO):
        async def pr_file_diff(self, project, repo_id, pr_id, path):
            calls.append(path)
            return await super().pr_file_diff(project, repo_id, pr_id, path)

    monkeypatch.setattr(ai, "ADOClient", TrackingADO)
    msg = {"tool_calls": [{"function": {"name": "suggest_review_comments",
                                        "arguments": json.dumps({"summary": "ok", "comments": []})}}]}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))

    out = await ai.review_pr("home", "r1", 12, path="/src/x.py")
    assert calls == ["/src/x.py"]  # only the requested file was diffed
    assert out["comments"] == []


@pytest.mark.asyncio
async def test_review_pr_nothing_reviewable(monkeypatch):
    class BinaryOnlyADO(_ReviewADO):
        async def pr_files(self, project, repo_id, pr_id):
            return {"iteration": 1, "sourceCommit": "s", "targetCommit": "t",
                    "files": [{"path": "/logo.png", "originalPath": None, "changeType": "edit"}]}

    monkeypatch.setattr(ai, "ADOClient", BinaryOnlyADO)

    async def must_not_call(*a, **k):
        raise AssertionError("model must not be invoked with no reviewable diffs")

    monkeypatch.setattr(copilot, "_invoke", must_not_call)
    out = await ai.review_pr("home", "r1", 12)
    assert out["filesReviewed"] == 0 and out["comments"] == []


# -- explain file -------------------------------------------------------------------


class _FileADO:
    def __init__(self, *a, **k):
        pass

    async def get_file(self, project, repo_id, path, version=None, version_type="branch"):
        if path == "/logo.png":
            return {"path": path, "binary": True, "truncated": False, "content": ""}
        return {"path": path, "binary": False, "truncated": False,
                "content": "def add(a, b):\n    return a + b\n"}


@pytest.mark.asyncio
async def test_explain_file(monkeypatch):
    monkeypatch.setattr(ai, "ADOClient", _FileADO)
    msg = {"tool_calls": [{"function": {"name": "explain_file", "arguments": json.dumps({
        "explanation": "This file adds two numbers together for the calculator feature.",
        "keyPoints": "- adds numbers\n- used by the calculator",
    })}}]}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))

    out = await ai.explain_file("home", "r1", "/src/math.py", "dev")
    assert "adds two numbers" in out["explanation"]
    assert out["keyPoints"].startswith("- adds")


@pytest.mark.asyncio
async def test_explain_binary_short_circuits(monkeypatch):
    monkeypatch.setattr(ai, "ADOClient", _FileADO)

    async def must_not_call(*a, **k):
        raise AssertionError("model must not be invoked for binary files")

    monkeypatch.setattr(copilot, "_invoke", must_not_call)
    out = await ai.explain_file("home", "r1", "/logo.png", "dev")
    assert "binary" in out["explanation"].lower()


@pytest.mark.asyncio
async def test_explain_no_explanation_raises(monkeypatch):
    monkeypatch.setattr(ai, "ADOClient", _FileADO)
    msg = {"content": "I cannot explain this."}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg))
    with pytest.raises(ai.SuggestionParseError):
        await ai.explain_file("home", "r1", "/src/math.py", "dev")


@pytest.mark.asyncio
async def test_draft_lands_in_prompt(monkeypatch):
    captured: dict = {}
    msg = {"content": json.dumps({"title": "T", "description": "D"})}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg, captured))
    await ai.suggest_work_item("home", {"type": "Task", "title": "fix it", "description": ""})
    user_msg = captured["messages"][1]["content"]
    assert "type: Task" in user_msg and "title: fix it" in user_msg
    assert "description: (empty)" in user_msg