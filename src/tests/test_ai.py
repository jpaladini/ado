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


@pytest.mark.asyncio
async def test_draft_lands_in_prompt(monkeypatch):
    captured: dict = {}
    msg = {"content": json.dumps({"title": "T", "description": "D"})}
    monkeypatch.setattr(copilot, "_invoke", _fake_invoke(msg, captured))
    await ai.suggest_work_item("home", {"type": "Task", "title": "fix it", "description": ""})
    user_msg = captured["messages"][1]["content"]
    assert "type: Task" in user_msg and "title: fix it" in user_msg
    assert "description: (empty)" in user_msg