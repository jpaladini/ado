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
import re
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

import httpx

from app import genie
from app.ado.analytics import AnalyticsClient, OPEN_CATEGORIES
from app.ado.client import ADOClient
from app.config import settings

log = logging.getLogger(__name__)

SECRET_SCOPE = "ado"
MAX_TURNS = 8  # model-call iterations per user message
TOOL_RESULT_LIMIT = 6000  # chars of tool output fed back to the model
DIFF_LINE_LIMIT = 300  # max diff lines fed to the model per file
DIFF_CHAR_LIMIT = 5000  # < TOOL_RESULT_LIMIT so json.dumps never chops mid-structure
FILE_LINE_LIMIT = 200  # default get_file window


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
    _schema(
        "list_pr_files",
        "Files changed in a pull request (path, changeType).",
        {
            "prId": {"type": "integer"},
            "repositoryId": {"type": "string", "description": "From list_pull_requests results — never guess."},
        },
        ["prId", "repositoryId"],
    ),
    _schema(
        "get_pr_file_diff",
        "Unified diff for one file in a PR (may be truncated; includes +/- line counts). "
        "Line numbers on '+' lines are the RIGHT side — use them for comment_on_pr_file.",
        {
            "prId": {"type": "integer"},
            "repositoryId": {"type": "string", "description": "From list_pull_requests results — never guess."},
            "path": {"type": "string", "description": "File path from list_pr_files."},
        },
        ["prId", "repositoryId", "path"],
    ),
    _schema(
        "list_pr_threads",
        "Existing review comment threads on a PR (file-anchored and general).",
        {
            "prId": {"type": "integer"},
            "repositoryId": {"type": "string", "description": "From list_pull_requests results — never guess."},
        },
        ["prId", "repositoryId"],
    ),
    _schema(
        "get_file",
        "Read a file from a repo branch (windowed to 200 lines; pass startLine/endLine for more).",
        {
            "repositoryId": {"type": "string", "description": "From list_pull_requests or the repos list."},
            "path": {"type": "string"},
            "branch": {"type": "string", "description": "Defaults to the repo's default branch."},
            "startLine": {"type": "integer"},
            "endLine": {"type": "integer"},
        },
        ["repositoryId", "path"],
    ),
    _schema(
        "query_analytics_history",
        "Ask Databricks Genie a natural-language BI question over the INGESTED analytics "
        "tables (Delta, refreshed daily — NOT real-time). Use for trends, history, and "
        "aggregations over time; use the other tools for current/live state. Returns "
        "text plus a result table when the question is tabular.",
        {"question": {"type": "string", "description": "A self-contained analytics question."}},
        ["question"],
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
    _schema(
        "comment_on_pr",
        "PROPOSE a general comment on a pull request. Not executed immediately.",
        {
            "prId": {"type": "integer"},
            "repositoryId": {"type": "string", "description": "From list_pull_requests results — never guess."},
            "comment": {"type": "string"},
        },
        ["prId", "repositoryId", "comment"],
    ),
    _schema(
        "comment_on_pr_file",
        "PROPOSE a review comment anchored to a file+line in a PR. Use a line number "
        "from the RIGHT (new) side of a diff you actually read. Not executed immediately.",
        {
            "prId": {"type": "integer"},
            "repositoryId": {"type": "string", "description": "From list_pull_requests results — never guess."},
            "path": {"type": "string"},
            "line": {"type": "integer"},
            "comment": {"type": "string"},
        },
        ["prId", "repositoryId", "path", "line", "comment"],
    ),
]

WRITE_TOOL_NAMES = {t["function"]["name"] for t in WRITE_TOOLS}
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS


def _truncate_diff(d: dict[str, Any]) -> dict[str, Any]:
    """Cap a diff payload for the model, cutting on line boundaries only."""
    diff = d.get("diff") or ""
    lines = diff.split("\n")
    total = len(lines)
    kept: list[str] = []
    chars = 0
    for line in lines[:DIFF_LINE_LIMIT]:
        if chars + len(line) + 1 > DIFF_CHAR_LIMIT:
            break
        kept.append(line)
        chars += len(line) + 1
    if len(kept) < total:
        d = {
            **d,
            "diff": "\n".join(kept),
            "truncatedNote": (
                f"diff truncated: showing {len(kept)} of {total} lines — "
                "use get_file with startLine/endLine to read specific regions"
            ),
        }
    return d


def _window_file(f: dict[str, Any], start: int | None, end: int | None) -> dict[str, Any]:
    """Slice file content to a line window (1-indexed, inclusive)."""
    lines = (f.get("content") or "").split("\n")
    total = len(lines)
    lo = max(1, int(start or 1))
    hi = min(total, int(end or (lo + FILE_LINE_LIMIT - 1)))
    return {
        "path": f.get("path"),
        "binary": f.get("binary", False),
        "lines": f"{lo}-{hi}",
        "totalLines": total,
        "content": "\n".join(lines[lo - 1 : hi]),
    }


async def _run_read_tool(name: str, args: dict[str, Any], project: str) -> Any:
    if name == "get_analytics_summary":
        a = AnalyticsClient()
        by_cat = await a.count_by_state_category(project)
        return {
            "byCategory": by_cat,
            "open": sum(v for k, v in by_cat.items() if k in OPEN_CATEGORIES),
            "total": sum(by_cat.values()),
        }
    if name == "query_analytics_history":
        try:
            ans = await genie.ask(str(args["question"]))
        except genie.GenieNotConfigured as e:
            return {"error": str(e)}
        return {
            "text": " ".join(ans.get("text") or []),
            "queryDescription": ans.get("queryDescription"),
            "columns": ans.get("columns") or [],
            "rows": (ans.get("rows") or [])[:50],
            "note": "Data is batch (refreshed daily / on demand), not real-time.",
        }
    c = ADOClient()
    if name == "list_pr_files":
        return await c.pr_files(project, str(args["repositoryId"]), int(args["prId"]))
    if name == "get_pr_file_diff":
        d = await c.pr_file_diff(project, str(args["repositoryId"]), int(args["prId"]), str(args["path"]))
        return _truncate_diff(d)
    if name == "list_pr_threads":
        return await c.list_pr_threads(project, str(args["repositoryId"]), int(args["prId"]))
    if name == "get_file":
        rid = str(args["repositoryId"])
        branch = args.get("branch")
        if not branch:
            repos = await c.list_repos(project)
            match = next((r for r in repos if r["id"] == rid or r["name"] == rid), None)
            branch = (match or {}).get("defaultBranch") or "main"
        f = await c.get_file(project, rid, str(args["path"]), version=str(branch))
        if f["binary"]:
            return {"path": f["path"], "binary": True}
        return _window_file(f, args.get("startLine"), args.get("endLine"))
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
- NEVER guess work item IDs. Only use IDs you have seen in a read tool result in
  this conversation; when unsure, call list_work_items first. Proposals against
  nonexistent items are rejected.
- When a request affects several items, make a write tool call for EACH item — one
  proposal per item. Tool calls must go through the tool-calling mechanism ONLY;
  never write a tool call as text in your answer. If you have more calls to make,
  keep making them — you are re-prompted after each batch of results — and give the
  plain-language summary only once everything is proposed.
- Prior assistant turns may end with a "[Proposal outcomes: ...]" note recording
  what the user applied or dismissed and what failed — use it to decide next steps
  and never re-propose something already applied.
- Before assigning anyone, resolve their email with search_identities.
- For PR review: list_pull_requests → list_pr_files → get_pr_file_diff per file you
  care about; propose feedback with comment_on_pr_file anchored to RIGHT-side line
  numbers you actually saw in a diff, or comment_on_pr for overall notes. Never guess
  prId or repositoryId — both come from list_pull_requests results.
- Two data planes: read tools are LIVE; query_analytics_history is BATCH (Delta,
  refreshed daily). Use it for trends/history and say so when you do — never present
  batch numbers as real-time.
- Be concise. Answer in plain sentences; no markdown headers.
"""


async def _verify_write_target(name: str, args: dict[str, Any], project: str) -> str | None:
    """Reject proposals that target something that doesn't exist (models sometimes
    assume sequential IDs). Returns an error string, or None if OK."""
    if name in ("update_work_item", "add_work_item_comment") and args.get("id") is not None:
        try:
            await ADOClient().get_work_item(int(args["id"]))
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return (
                    f"Work item {args['id']} does not exist. Do not guess IDs — call "
                    "list_work_items or get_work_item to find the real ones, then re-propose."
                )
            return f"Could not verify work item {args['id']}: ADO returned {e.response.status_code}"
        except Exception as e:
            return f"Could not verify work item {args['id']}: {e}"

    if name in ("comment_on_pr", "comment_on_pr_file"):
        if args.get("prId") is None or not args.get("repositoryId"):
            return (
                "comment_on_pr* needs prId and repositoryId from list_pull_requests "
                "results — look them up first."
            )
        try:
            await ADOClient().get_pull_request(project, str(args["repositoryId"]), int(args["prId"]))
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return (
                    f"PR {args['prId']} does not exist in that repository. "
                    "Call list_pull_requests to find the real id, then re-propose."
                )
            return f"Could not verify PR {args['prId']}: ADO returned {e.response.status_code}"
        except Exception as e:
            return f"Could not verify PR {args['prId']}: {e}"

    return None


async def _invoke(
    endpoint: str,
    messages: list[dict],
    tools: list[dict],
    *,
    tool_choice: dict[str, Any] | None = None,
    temperature: float | None = None,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """One chat-completions call to the serving endpoint (SP/PAT ambient auth)."""
    w = _workspace_client()
    headers = w.config.authenticate()  # refreshes tokens as needed
    url = f"{w.config.host.rstrip('/')}/serving-endpoints/{endpoint}/invocations"
    payload: dict[str, Any] = {"messages": messages, "tools": tools, "max_tokens": max_tokens}
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if temperature is not None:
        payload["temperature"] = temperature
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def _content_text(content: Any) -> str:
    """Chat content may be a string or a list of typed blocks (e.g. reasoning models)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


_TOOL_NAME_ALT = "|".join(sorted(t["function"]["name"] for t in ALL_TOOLS))
_TEXT_CALL_RE = re.compile(rf"\b({_TOOL_NAME_ALT})\s*\(([^()]*)\)")
_ARG_RE = re.compile(r"""(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^,()]+)""")


def _parse_text_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Llama-family models sometimes emit a tool call as plain text — e.g.
    `update_work_item(id=2, tags="triage")` — instead of a structured tool_call
    (typically the 2nd+ call in a multi-item request). Lift those into real tool
    calls so proposals aren't silently lost, and strip them (plus the stray
    'assistant' template token) from the visible text."""
    calls: list[dict[str, Any]] = []

    def lift(m: re.Match) -> str:
        args: dict[str, Any] = {}
        for am in _ARG_RE.finditer(m.group(2)):
            k, v = am.group(1), am.group(2).strip()
            if v[:1] in "\"'" and v[-1:] == v[:1]:
                v = v[1:-1]
            else:
                try:
                    v = int(v)
                except ValueError:
                    pass
            args[k] = v
        calls.append({
            "id": f"textcall{len(calls)}",
            "type": "function",
            "function": {"name": m.group(1), "arguments": json.dumps(args)},
        })
        return ""

    cleaned = _TEXT_CALL_RE.sub(lift, text)
    cleaned = re.sub(r"(^|\n)\s*assistant\s*(\n|$)", r"\1", cleaned).strip()
    return cleaned, calls


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

            tcs = list(msg.get("tool_calls") or [])
            text = _content_text(msg.get("content"))
            cleaned, lifted = _parse_text_tool_calls(text) if text else (text, [])
            tcs += lifted
            # Echo the assistant message back so the endpoint sees its own turn —
            # with any text-form calls moved into structured tool_calls.
            messages.append({
                "role": "assistant",
                "content": cleaned if lifted else (msg.get("content") or ""),
                **({"tool_calls": tcs} if tcs else {}),
            })

            if not tcs:
                reply = cleaned
                break

            for tc in tcs:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name in WRITE_TOOL_NAMES:
                    with _span(f"verify:{name}") as vs:
                        problem = await _verify_write_target(name, args, project)
                        if vs:
                            vs.set_inputs({"id": args.get("id")})
                            vs.set_outputs({"rejected": problem})
                    if problem:
                        result: Any = {"error": problem}
                    else:
                        pid = f"p{len(proposals) + 1}"
                        proposals.append({"id": pid, "tool": name, "args": args})
                        result = {
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
