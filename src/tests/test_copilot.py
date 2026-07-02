"""Agent-loop tests: scripted endpoint responses, no workspace or ADO needed."""
import json

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
