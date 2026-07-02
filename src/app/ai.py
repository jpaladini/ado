"""Single-shot AI suggestions (work-item drafting) over the FMAPI endpoint.

Unlike the copilot agent loop, this is one forced function call: given a partial
work-item draft, the model returns completed fields that the UI writes into the
form for the user to review — the form itself is the propose-then-apply gate, so
nothing here mutates ADO. Shares the endpoint config, invoke plumbing, and MLflow
tracing with app.copilot.
"""
import json
import logging
import re
from typing import Any

from app import copilot
from app.copilot import CopilotNotConfigured, _content_text, _schema, _span, resolve_endpoint

__all__ = ["suggest_work_item", "SuggestionParseError", "CopilotNotConfigured"]

log = logging.getLogger(__name__)


class SuggestionParseError(RuntimeError):
    """The model responded, but no usable suggestion could be parsed."""


_SUGGESTION_TOOL = _schema(
    "suggest_work_item",
    "Return the completed work item draft.",
    {
        "title": {"type": "string", "description": "Concise, imperative, <=80 chars."},
        "description": {
            "type": "string",
            "description": "Plain text with line breaks; context, scope, approach.",
        },
        "tags": {"type": "string", "description": "2-4 semicolon-separated tags, e.g. 'auth; p1'."},
        "type": {
            "type": "string",
            "description": "Suggested work item type ONLY if the draft's type looks wrong; else omit.",
        },
        "acceptanceCriteria": {
            "type": "string",
            "description": "Plain-text bulleted list, one criterion per line, '- ' prefix.",
        },
    },
    ["title", "description", "tags"],
)

_SUGGEST_SYSTEM = (
    'You complete Azure DevOps work item drafts for the project "{project}".\n'
    "Given a partial draft, produce a filled-out version by calling the "
    "suggest_work_item tool exactly once. Rules:\n"
    "- Keep the user's intent and any concrete facts; never invent people, dates, or IDs.\n"
    "- Title: one imperative sentence. Description: 3-8 short lines — what, why, and "
    "rough approach; plain text only, no markdown headers.\n"
    "- acceptanceCriteria: 2-5 testable '- ' bullets.\n"
    "- tags: 2-4 short lowercase topical tags, semicolon-separated.\n"
    "- Respond ONLY with the tool call; no prose."
)

_SUGGEST_USER = "Draft work item:\ntype: {type}\ntitle: {title}\ndescription: {description}"

# Text-form fallback for models that emit the call as prose (same patterns as
# copilot._parse_text_tool_calls, but keyed to this module's single tool name —
# the copilot regex only matches its own registry).
_TEXT_CALL_RE = re.compile(r"\bsuggest_work_item\s*\(([^()]*)\)")
_ARG_RE = re.compile(r"""(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^,()]+)""")

_FIELDS = ("title", "description", "tags", "type", "acceptanceCriteria")


def _parse_text_call(text: str) -> dict[str, Any] | None:
    m = _TEXT_CALL_RE.search(text)
    if not m:
        return None
    args: dict[str, Any] = {}
    for am in _ARG_RE.finditer(m.group(1)):
        k, v = am.group(1), am.group(2).strip()
        if v[:1] in "\"'" and v[-1:] == v[:1]:
            v = v[1:-1]
        args[k] = v
    return args or None


def _extract_suggestion(msg: dict[str, Any]) -> dict[str, Any]:
    """Parse the suggestion from a chat message: structured tool call, then
    text-form call, then bare-JSON content."""
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        if fn.get("name") == "suggest_work_item":
            try:
                return json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                pass

    text = _content_text(msg.get("content")).strip()
    if text:
        parsed = _parse_text_call(text)
        if parsed:
            return parsed
        if text.startswith("{"):
            try:
                loaded = json.loads(text)
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                pass
    raise SuggestionParseError("no tool call or JSON object in the model response")


def _normalize(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in _FIELDS:
        v = str(raw.get(k) or "").strip()
        if v:
            out[k] = v
    if "tags" in out:
        out["tags"] = "; ".join(t.strip() for t in re.split(r"[,;]", out["tags"]) if t.strip())
    if not out.get("title") and not out.get("description"):
        raise SuggestionParseError("suggestion had neither title nor description")
    return out


async def suggest_work_item(project: str, draft: dict[str, Any]) -> dict[str, Any]:
    """draft: {type?, title?, description?}, at least one of title/description set.
    Returns {"suggestion": {title, description, tags, type?, acceptanceCriteria?},
    "endpoint": <name>}."""
    endpoint = resolve_endpoint()
    messages = [
        {"role": "system", "content": _SUGGEST_SYSTEM.format(project=project)},
        {
            "role": "user",
            "content": _SUGGEST_USER.format(
                type=str(draft.get("type") or "(unspecified)"),
                title=str(draft.get("title") or "(empty)"),
                description=str(draft.get("description") or "(empty)"),
            ),
        },
    ]

    with _span("ai.suggest", endpoint=endpoint, project=project) as span:
        if span:
            span.set_inputs({"draft": {k: str(v)[:200] for k, v in draft.items() if v}})
        data = await copilot._invoke(
            endpoint,
            messages,
            [_SUGGESTION_TOOL],
            tool_choice={"type": "function", "function": {"name": "suggest_work_item"}},
            temperature=0.2,
        )
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        suggestion = _normalize(_extract_suggestion(msg))
        if span:
            span.set_outputs({"suggestion": suggestion})

    return {"suggestion": suggestion, "endpoint": endpoint}
