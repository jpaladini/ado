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
from app.ado.client import ADOClient
from app.copilot import CopilotNotConfigured, _content_text, _schema, _span, resolve_endpoint

__all__ = ["suggest_work_item", "review_pr", "SuggestionParseError", "CopilotNotConfigured"]

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


# -- in-place PR review ------------------------------------------------------------
#
# One forced function call over server-fetched diffs. Because *we* hand the model
# the diff text, we can also validate every suggested line number against the
# actual right-side lines of the hunks — suggestions pointing at lines that are
# not part of the change are clamped to the nearest changed line or dropped.

REVIEW_MAX_FILES = 10
REVIEW_DIFF_CHARS = 4000  # per-file diff budget in the prompt
SEVERITIES = ("nit", "suggestion", "issue")

_REVIEW_TOOL = _schema(
    "suggest_review_comments",
    "Return the code review: an overall summary plus zero or more line-anchored comments.",
    {
        "summary": {"type": "string", "description": "1-3 sentences on the change overall."},
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path exactly as given."},
                    "line": {"type": "integer", "description": "RIGHT-side (new file) line number of a + line in that file's diff."},
                    "comment": {"type": "string", "description": "Concise, actionable, specific."},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                },
                "required": ["path", "line", "comment", "severity"],
            },
        },
    },
    ["summary", "comments"],
)

_REVIEW_SYSTEM = (
    "You are a careful senior code reviewer. You receive unified diffs for a pull "
    "request and respond by calling suggest_review_comments exactly once. Rules:\n"
    "- Comment ONLY where something is genuinely worth flagging: bugs, risky edge "
    "cases, security issues, dead code, naming that will confuse. No praise comments, "
    "no restating the diff.\n"
    "- At most 4 comments per file; zero is a fine answer for a clean diff.\n"
    "- line must be the RIGHT-side (new-file) line number of a '+' line you can see "
    "in that file's hunk headers. path must match exactly.\n"
    "- severity: nit (style), suggestion (would improve), issue (should fix).\n"
    "- Keep the summary to 1-3 plain sentences."
)


def right_side_lines(diff: str) -> set[int]:
    """Right-side (new file) line numbers of '+' lines in a unified diff —
    the only lines a review comment can be anchored to."""
    commentable: set[int] = set()
    new_ln = 0
    for line in diff.split("\n"):
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
        if m:
            new_ln = int(m.group(1))
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            commentable.add(new_ln)
            new_ln += 1
        elif line.startswith("-"):
            continue
        else:
            new_ln += 1
    return commentable


def _validate_comments(
    raw: list[dict[str, Any]], lines_by_path: dict[str, set[int]]
) -> tuple[list[dict[str, Any]], int]:
    """Keep only comments whose target file was reviewed; clamp line numbers to the
    nearest actually-changed line. Returns (valid_comments, dropped_count)."""
    valid: list[dict[str, Any]] = []
    dropped = 0
    for c in raw:
        path = str(c.get("path") or "")
        text = str(c.get("comment") or "").strip()
        allowed = lines_by_path.get(path)
        if not allowed and path and not path.startswith("/"):
            path = f"/{path}"
            allowed = lines_by_path.get(path)
        if not allowed or not text:
            dropped += 1
            continue
        try:
            line = int(c.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        if line not in allowed:
            line = min(allowed, key=lambda n: abs(n - line))  # clamp to nearest + line
        severity = str(c.get("severity") or "suggestion")
        valid.append(
            {
                "path": path,
                "line": line,
                "comment": text,
                "severity": severity if severity in SEVERITIES else "suggestion",
            }
        )
    return valid, dropped


def _extract_review(msg: dict[str, Any]) -> dict[str, Any]:
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        if fn.get("name") == "suggest_review_comments":
            try:
                return json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                pass
    text = _content_text(msg.get("content")).strip()
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass
    raise SuggestionParseError("no review tool call or JSON object in the model response")


async def review_pr(
    project: str, repo_id: str, pr_id: int, path: str | None = None
) -> dict[str, Any]:
    """Review a PR's diffs (or a single file when path is given). Returns
    {summary, comments: [{path, line, comment, severity}], filesReviewed,
    skipped, dropped, endpoint}. Nothing is posted — the UI applies each
    suggestion through the normal PR-thread route."""
    endpoint = resolve_endpoint()
    c = ADOClient()
    info = await c.pr_files(project, repo_id, pr_id)
    files = [f for f in info["files"] if not path or f["path"] == path][:REVIEW_MAX_FILES]

    sections: list[str] = []
    lines_by_path: dict[str, set[int]] = {}
    skipped: list[str] = []
    for f in files:
        d = await c.pr_file_diff(project, repo_id, pr_id, f["path"])
        if d.get("binary") or d.get("tooLarge") or not d.get("diff"):
            skipped.append(f["path"])
            continue
        diff_text = d["diff"][:REVIEW_DIFF_CHARS]
        lines_by_path[f["path"]] = right_side_lines(diff_text)
        sections.append(f"### {f['path']} ({f.get('changeType')})\n{diff_text}")

    if not sections:
        return {
            "summary": "Nothing reviewable — only binary, oversized, or empty diffs.",
            "comments": [],
            "filesReviewed": 0,
            "skipped": skipped,
            "dropped": 0,
            "endpoint": endpoint,
        }

    messages = [
        {"role": "system", "content": _REVIEW_SYSTEM},
        {"role": "user", "content": f"Pull request !{pr_id} diffs:\n\n" + "\n\n".join(sections)},
    ]

    with _span("ai.review", endpoint=endpoint, project=project) as span:
        if span:
            span.set_inputs({"prId": pr_id, "path": path, "files": list(lines_by_path)})
        data = await copilot._invoke(
            endpoint,
            messages,
            [_REVIEW_TOOL],
            tool_choice={"type": "function", "function": {"name": "suggest_review_comments"}},
            temperature=0.2,
            max_tokens=3000,
        )
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        review = _extract_review(msg)
        comments, dropped = _validate_comments(list(review.get("comments") or []), lines_by_path)
        if span:
            span.set_outputs({"comments": len(comments), "dropped": dropped,
                              "summary": str(review.get("summary") or "")[:300],
                              "usage": data.get("usage")})

    return {
        "summary": str(review.get("summary") or "").strip(),
        "comments": comments,
        "filesReviewed": len(lines_by_path),
        "skipped": skipped,
        "dropped": dropped,
        "endpoint": endpoint,
    }


# -- plain-language file explanation --------------------------------------------------

EXPLAIN_MAX_CHARS = 12_000

_EXPLAIN_TOOL = _schema(
    "explain_file",
    "Return the plain-language explanation of the file.",
    {
        "explanation": {
            "type": "string",
            "description": "3-6 short sentences a non-technical reader understands.",
        },
        "keyPoints": {
            "type": "string",
            "description": "2-4 '- ' bullets: the key things this file handles. Plain language.",
        },
    },
    ["explanation"],
)

_EXPLAIN_SYSTEM = (
    "You explain source files to smart people who do not write code. Call explain_file "
    "exactly once. Rules:\n"
    "- Say what the file IS, what it does for the product, and why someone would care — "
    "in plain language. Name the product concepts, not the syntax.\n"
    "- No jargon (no 'async', 'endpoint', 'class' etc. without a plain gloss). Never "
    "quote code.\n"
    "- 3-6 short sentences, plus 2-4 keyPoints bullets.\n"
    "- If the content is truncated, explain what is visible without guessing the rest."
)


async def explain_file(project: str, repo_id: str, path: str, branch: str) -> dict[str, Any]:
    """Fetch a file and return {explanation, keyPoints?, endpoint} for a
    non-technical audience. Read-only; nothing is written anywhere."""
    endpoint = resolve_endpoint()
    f = await ADOClient().get_file(project, repo_id, path, version=branch)
    if f["binary"]:
        return {
            "explanation": "This is a binary file (an image or other non-text asset) — there is no code to explain.",
            "keyPoints": "",
            "endpoint": endpoint,
        }
    content = (f["content"] or "")[:EXPLAIN_MAX_CHARS]
    truncated = len(f["content"] or "") > EXPLAIN_MAX_CHARS

    messages = [
        {"role": "system", "content": _EXPLAIN_SYSTEM},
        {
            "role": "user",
            "content": f"File: {path} (branch {branch})"
            + (" — content truncated" if truncated else "")
            + f"\n\n{content}",
        },
    ]

    with _span("ai.explain", endpoint=endpoint, project=project) as span:
        if span:
            span.set_inputs({"path": path, "branch": branch, "chars": len(content)})
        data = await copilot._invoke(
            endpoint,
            messages,
            [_EXPLAIN_TOOL],
            tool_choice={"type": "function", "function": {"name": "explain_file"}},
            temperature=0.2,
        )
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        raw = _extract_named_call(msg, "explain_file")
        explanation = str(raw.get("explanation") or "").strip()
        if not explanation:
            raise SuggestionParseError("model returned no explanation")
        out = {
            "explanation": explanation,
            "keyPoints": str(raw.get("keyPoints") or "").strip(),
            "endpoint": endpoint,
        }
        if span:
            span.set_outputs({"explanation": explanation[:300], "usage": data.get("usage")})
    return out


def _extract_named_call(msg: dict[str, Any], tool_name: str) -> dict[str, Any]:
    """Structured tool call by name, else bare-JSON content, else error."""
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        if fn.get("name") == tool_name:
            try:
                return json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                pass
    text = _content_text(msg.get("content")).strip()
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass
    raise SuggestionParseError(f"no {tool_name} tool call or JSON object in the model response")


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
            span.set_outputs({"suggestion": suggestion, "usage": data.get("usage")})

    return {"suggestion": suggestion, "endpoint": endpoint}
