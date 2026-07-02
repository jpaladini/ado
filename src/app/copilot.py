"""AI copilot: a tool-calling agent loop over a Databricks FMAPI serving endpoint.

Design contract (see PLAN.md §5a 4D):
- **Read tools execute immediately**, through the same ADO client the REST routes
  use — the copilot can never see more than the app itself.
- **Write tools never execute here.** Each write tool call is returned as a
  *proposal*; the UI renders it with an Apply button that calls the normal REST
  route, so audit logging and permissions are identical to a human click.
- The serving endpoint name is per-workspace config (env `COPILOT_ENDPOINT` or
  secret `ado/copilot_endpoint`) — Databricks-hosted models only.
- MLflow Tracing records each turn (question → model calls → tool runs) when an
  experiment is configured (env `MLFLOW_EXPERIMENT_ID` or secret
  `ado/mlflow_experiment_id`). Tracing failures never break a chat turn.
"""
import base64
import json
import logging
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

import httpx

from app.ado.analytics import AnalyticsClient, OPEN_CATEGORIES
from app.ado.client import ADOClient
from app.config import settings

log = logging.getLogger(__name__)

SECRET_SCOPE = "ado"
MAX_TURNS = 8  # model-call iterations per user message
TOOL_RESULT_LIMIT = 6000  # chars of tool output fed back to the model


class CopilotNotConfigured(RuntimeError):
    """Raised when no serving endpoint is configured."""


@lru_cache(maxsize=1)
def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _secret(key: str) -> str:
    try:
        w = _workspace_client()
        raw = w.secrets.get_secret(SECRET_SCOPE, key).value or ""
        return base64.b64decode(raw).decode().strip()
    except Exception as e:  # missing scope/key, no auth — all mean "not set"
        log.info("secret %s/%s lookup failed: %s", SECRET_SCOPE, key, e)
        return ""


@lru_cache(maxsize=1)
def resolve_endpoint() -> str:
    ep = settings.copilot_endpoint or _secret("copilot_endpoint")
    if not ep:
        raise CopilotNotConfigured(
            "No copilot endpoint configured. Set the ado/copilot_endpoint secret "
            "(a Databricks FMAPI chat endpoint name, e.g. databricks-llama-4-maverick)."
        )
    return ep


@lru_cache(maxsize=1)
def resolve_experiment_id() -> str:
    return settings.mlflow_experiment_id or _secret("mlflow_experiment_id")


def copilot_available() -> bool:
    try:
        resolve_endpoint()
        return True
    except CopilotNotConfigured:
        return False


# -- MLflow tracing (optional, never fatal) ------------------------------------

_mlflow_ready: bool | None = None


def _mlflow():
    """Return the mlflow module configured for our experiment, or None."""
    global _mlflow_ready
    if _mlflow_ready is False:
        return None
    try:
        exp = resolve_experiment_id()
        if not exp:
            _mlflow_ready = False
            return None
        import mlflow

        if _mlflow_ready is None:
            mlflow.set_tracking_uri("databricks")
            mlflow.set_experiment(experiment_id=exp)
            _mlflow_ready = True
        return mlflow
    except Exception as e:
        log.info("mlflow tracing unavailable: %s", e)
        _mlflow_ready = False
        return None


def _span(name: str, **attrs: Any):
    """A tracing span context manager, or a no-op when tracing is off."""
    m = _mlflow()
    if not m:
        return nullcontext(None)
    try:
        return m.start_span(name=name, attributes=attrs or None)
    except Exception:
        return nullcontext(None)


# -- tool registry --------------------------------------------------------------

def _schema(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


_WI_PROPS = {
    "title": {"type": "string"},
    "description": {"type": "string", "description": "Plain text; line breaks preserved."},
    "assignedTo": {"type": "string", "description": "User email (find via search_identities)."},
    "tags": {"type": "string", "description": "Semicolon-separated, e.g. 'auth; p1'."},
    "iterationPath": {"type": "string", "description": "e.g. 'home\\\\Sprint 1'."},
}

READ_TOOLS: list[dict[str, Any]] = [
    _schema(
        "list_work_items",
        "List the project's most recently changed work items (id, title, state, type, assignee, tags).",
        {"top": {"type": "integer", "description": "Max items (default 50)."}},
        [],
    ),
    _schema(
        "get_work_item",
        "Full detail for one work item: description, tags, iteration, area, created/changed info.",
        {"id": {"type": "integer"}},
        ["id"],
    ),
    _schema(
        "list_work_item_comments",
        "Comment history for a work item (newest first).",
        {"id": {"type": "integer"}},
        ["id"],
    ),
    _schema(
        "search_identities",
        "Search org users by name or email — use before assigning anyone.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _schema(
        "list_pull_requests",
        "List pull requests in the project.",
        {"status": {"type": "string", "enum": ["active", "completed", "abandoned", "all"]}},
        [],
    ),
    _schema(
        "list_builds",
        "Recent pipeline builds (status, result, branch, requester).",
        {"top": {"type": "integer"}},
        [],
    ),
    _schema(
        "get_analytics_summary",
        "Near-live aggregate: work item counts by state category, open and total counts.",
        {},
        [],
    ),
]

WRITE_TOOLS: list[dict[str, Any]] = [
    _schema(
        "create_work_item",
        "PROPOSE creating a work item. Not executed immediately: the user reviews and applies it.",
        {"type": {"type": "string", "description": "Work item type, e.g. Task, Issue, Epic."}, **_WI_PROPS},
        ["type", "title"],
    ),
    _schema(
        "update_work_item",
        "PROPOSE updating fields on a work item (only include fields to change; "
        "empty assignedTo unassigns). Not executed immediately.",
        {"id": {"type": "integer"}, "state": {"type": "string"}, **_WI_PROPS},
        ["id"],
    ),
    _schema(
        "add_work_item_comment",
        "PROPOSE adding a comment to a work item. Not executed immediately.",
        {"id": {"type": "integer"}, "text": {"type": "string"}},
        ["id", "text"],
    ),
]

WRITE_TOOL_NAMES = {t["function"]["name"] for t in WRITE_TOOLS}
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS


async def _run_read_tool(name: str, args: dict[str, Any], project: str) -> Any:
    c = ADOClient()
    if name == "list_work_items":
        return await c.list_work_items(project, top=min(int(args.get("top") or 50), 200))
    if name == "get_work_item":
        return await c.get_work_item(int(args["id"]))
    if name == "list_work_item_comments":
        return await c.list_work_item_comments(project, int(args["id"]))
    if name == "search_identities":
        return await c.search_identities(str(args["query"]))
    if name == "list_pull_requests":
        return await c.list_pull_requests(project, status=args.get("status") or "active")
    if name == "list_builds":
        return await c.list_builds(project, top=min(int(args.get("top") or 25), 100))
    if name == "get_analytics_summary":
        a = AnalyticsClient()
        by_cat = await a.count_by_state_category(project)
        return {
            "byCategory": by_cat,
            "open": sum(v for k, v in by_cat.items() if k in OPEN_CATEGORIES),
            "total": sum(by_cat.values()),
        }
    raise ValueError(f"unknown read tool: {name}")


# -- the agent loop --------------------------------------------------------------

_SYSTEM = """You are the ADO Companion copilot for the Azure DevOps project "{project}".
You help manage work items, pull requests, and pipelines through the tools provided.

Rules:
- Use read tools freely to look things up before acting or answering.
- Write tools (create_work_item, update_work_item, add_work_item_comment) are
  PROPOSALS: they are recorded and shown to the user with an Apply button — they
  do not run when you call them. Propose confidently when asked to make changes,
  then briefly summarize what you proposed and note it awaits the user's approval.
- Before assigning anyone, resolve their email with search_identities.
- Be concise. Answer in plain sentences; no markdown headers.
"""


async def _invoke(endpoint: str, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
    """One chat-completions call to the serving endpoint (SP/PAT ambient auth)."""
    w = _workspace_client()
    headers = w.config.authenticate()  # refreshes tokens as needed
    url = f"{w.config.host.rstrip('/')}/serving-endpoints/{endpoint}/invocations"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url, headers=headers, json={"messages": messages, "tools": tools, "max_tokens": 2000}
        )
        resp.raise_for_status()
        return resp.json()


def _content_text(content: Any) -> str:
    """Chat content may be a string or a list of typed blocks (e.g. reasoning models)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


async def chat(project: str, message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run one user turn through the agent loop.

    history: prior turns as [{"role": "user"|"assistant", "content": str}, ...]
    Returns {reply, toolCalls, proposals, endpoint}.
    """
    endpoint = resolve_endpoint()
    messages: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM.format(project=project)}]
    for h in history or []:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    tool_calls_made: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    reply = ""

    with _span("copilot.turn", endpoint=endpoint, project=project) as turn:
        if turn:
            turn.set_inputs({"message": message, "history_turns": len(history or [])})

        for _ in range(MAX_TURNS):
            with _span("llm") as llm:
                data = await _invoke(endpoint, messages, ALL_TOOLS)
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                if llm:
                    llm.set_inputs({"messages": len(messages)})
                    llm.set_outputs({"finish_reason": choice.get("finish_reason"),
                                     "usage": data.get("usage")})

            tcs = msg.get("tool_calls") or []
            text = _content_text(msg.get("content"))
            # Echo the assistant message back verbatim so the endpoint sees its own turn.
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             **({"tool_calls": tcs} if tcs else {})})

            if not tcs:
                reply = text
                break

            for tc in tcs:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name in WRITE_TOOL_NAMES:
                    pid = f"p{len(proposals) + 1}"
                    proposals.append({"id": pid, "tool": name, "args": args})
                    result: Any = {
                        "proposed": True,
                        "proposalId": pid,
                        "note": "Recorded. The user will review and apply this change.",
                    }
                else:
                    with _span(f"tool:{name}") as ts:
                        if ts:
                            ts.set_inputs(args)
                        try:
                            result = await _run_read_tool(name, args, project)
                        except Exception as e:
                            result = {"error": f"{type(e).__name__}: {e}"}
                        if ts:
                            ts.set_outputs({"result": str(result)[:500]})
                    tool_calls_made.append({"name": name, "args": args})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "name": name,
                    "content": json.dumps(result, default=str)[:TOOL_RESULT_LIMIT],
                })
        else:
            reply = "I hit my step limit for this request — try narrowing it down."

        if turn:
            turn.set_outputs({"reply": reply[:1000],
                              "tools": [t["name"] for t in tool_calls_made],
                              "proposals": [p["tool"] for p in proposals]})

    return {
        "reply": reply,
        "toolCalls": tool_calls_made,
        "proposals": proposals,
        "endpoint": endpoint,
    }
