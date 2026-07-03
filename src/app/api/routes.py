"""API routes — the BFF surface the React app calls."""
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app import ai, codesearch, copilot, genie, insights, reportbuilder
from app.ado.analytics import AnalyticsClient, OPEN_CATEGORIES
from app.ado.client import ADOClient, ADOConfigError
from app.config import settings
from app.identity import request_user, user_email
from app.store import store

router = APIRouter(prefix="/api")

T = TypeVar("T")


async def _call(fn: Callable[[ADOClient], Awaitable[T]]) -> T:
    """Run an ADO client call, mapping config/HTTP errors to clean responses."""
    try:
        client = ADOClient()
        return await fn(client)
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        detail = f"Azure DevOps returned {e.response.status_code}"
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach Azure DevOps")


@router.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "ado_configured": settings.ado_configured,
        "genie_configured": genie.genie_available(),
        "copilot_configured": copilot.copilot_available(),
    }


@router.get("/me")
async def me() -> dict[str, object]:
    return await _call(lambda c: c.connection_data())


@router.get("/projects")
async def projects() -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_projects())}


@router.get("/projects/{project}/workitems")
async def work_items(project: str, top: int = Query(100, le=200)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_work_items(project, top=top))}


@router.get("/projects/{project}/workitems/{wid}")
async def work_item_detail(project: str, wid: int) -> dict[str, object]:
    return await _call(lambda c: c.get_work_item(wid))


@router.get("/projects/{project}/workitems/{wid}/comments")
async def work_item_comments(project: str, wid: int) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_work_item_comments(project, wid))}


@router.get("/projects/{project}/workitemtypes")
async def work_item_types(project: str) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_work_item_types(project))}


@router.get("/projects/{project}/iterations")
async def iterations(project: str) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_iterations(project))}


@router.get("/identities")
async def identities(q: str = Query(..., min_length=1)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.search_identities(q.strip()))}


@router.get("/projects/{project}/pullrequests")
async def pull_requests(
    project: str, status: str = Query("active"), top: int = Query(50, le=100)
) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_pull_requests(project, status=status, top=top))}


@router.get("/projects/{project}/builds")
async def builds(project: str, top: int = Query(25, le=100)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_builds(project, top=top))}


@router.get("/projects/{project}/repos")
async def repos(project: str) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_repos(project))}


_RANGE_DAYS = {"24h": 1, "7d": 7, "30d": 30}


@router.get("/projects/{project}/analytics")
async def analytics(project: str, range: str = Query("7d")) -> dict[str, object]:
    """Server-side aggregates (donut + open KPI) and a daily trend, via ADO Analytics
    OData. Degrades gracefully: if Analytics is unavailable, returns available=false so
    the dashboard can fall back to its client-side rollup."""
    days = _RANGE_DAYS.get(range, 7)
    by_category: dict[str, int] = {}
    trend: list[dict[str, object]] = []
    available = True
    try:
        client = AnalyticsClient()
        by_category = await client.count_by_state_category(project)
        try:
            trend = await client.open_trend(project, days)  # snapshots may be disabled
        except httpx.HTTPError:
            trend = []
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPError:
        available = False

    total = sum(by_category.values())
    open_count = sum(v for k, v in by_category.items() if k in OPEN_CATEGORIES)
    return {
        "byCategory": by_category,
        "open": open_count,
        "total": total,
        "trend": trend,
        "range": range,
        "available": available,
    }


_REPORT_RANGES = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, round(p * (len(sorted_vals) - 1))))
    return sorted_vals[k]


async def _gather_reports(project: str, range: str, types: str, assignees: str) -> dict[str, object]:
    """Shared by the Reports tab payload and the xlsx export. All aggregation is
    server-side OData $apply; KPIs are derived here from the same payloads."""
    import asyncio

    days = _REPORT_RANGES.get(range, 30)
    type_list = [t for t in (s.strip() for s in types.split(",")) if t] or None
    assignee_list = [a for a in (s.strip() for s in assignees.split(",")) if a] or None

    try:
        client = AnalyticsClient()
        created, completed, cycle, cfd_rows, open_items = await asyncio.gather(
            client.created_per_day(project, days, type_list, assignee_list),
            client.completed_per_day(project, days, type_list, assignee_list),
            client.cycle_time_items(project, days, type_list, assignee_list),
            client.cfd(project, days, type_list, assignee_list),
            client.open_items_detail(project, type_list, assignee_list),
        )
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Analytics returned {e.response.status_code}")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach ADO Analytics")

    # KPIs use 5-day-workweek durations (Jason: calendar-day cycle times are why
    # a custom Power BI semantic model existed — never again).
    cycle_bdays = sorted(float(i["cycleBdays"]) for i in cycle)
    created_total = sum(r["count"] for r in created)
    completed_total = sum(r["count"] for r in completed)
    return {
        "range": range,
        "days": days,
        "durationUnit": "businessDays",
        "filters": {"types": type_list or [], "assignees": assignee_list or []},
        "kpis": {
            "throughput": completed_total,
            "created": created_total,
            "netFlow": created_total - completed_total,
            "wip": len(open_items),
            "cycleP50": _percentile(cycle_bdays, 0.5),
            "cycleP85": _percentile(cycle_bdays, 0.85),
            "oldestWipDays": max((i["ageBdays"] for i in open_items), default=0),
        },
        "createdPerDay": created,
        "completedPerDay": completed,
        "cycleItems": cycle,
        "cfd": cfd_rows,
        "openItems": open_items,
    }


@router.get("/projects/{project}/reports")
async def reports(
    project: str,
    range: str = Query("30d"),
    types: str = Query(""),
    assignees: str = Query(""),
) -> dict[str, object]:
    """Everything the Reports tab draws, in one round trip."""
    return await _gather_reports(project, range, types, assignees)


_EXPORT_MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/projects/{project}/reports/export")
async def reports_export(
    project: str,
    range: str = Query("30d"),
    types: str = Query(""),
    assignees: str = Query(""),
    format: str = Query("xlsx"),
):
    """The same flow metrics as a download (all durations business days)."""
    from fastapi.responses import Response

    from app import exports

    if format not in _EXPORT_MEDIA:
        raise HTTPException(status_code=422, detail="format must be xlsx or pdf")
    payload = await _gather_reports(project, range, types, assignees)
    build = exports.reports_workbook if format == "xlsx" else exports.reports_pdf
    data = build(project, payload)
    fname = f"flow-metrics-{project}-{range}.{format}"
    return Response(
        content=data,
        media_type=_EXPORT_MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# -- global search (work items + code) ---------------------------------------------


@router.get("/projects/{project}/search")
async def global_search(
    project: str, q: str = Query(..., min_length=2), top: int = Query(20, le=50)
) -> dict[str, object]:
    """One round trip for the header search box: work items (ADO search service,
    WIQL fallback) + code (BFF grep index — the org has no Code Search extension).
    Each plane fails independently; the other still answers."""
    import asyncio

    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="query too short")

    try:
        client = ADOClient()
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async def work_items() -> dict[str, object]:
        try:
            return {"available": True, "results": await client.search_work_items(project, query, top)}
        except httpx.HTTPError as e:
            return {"available": False, "reason": f"work-item search failed: {e}", "results": []}

    async def pull_requests() -> dict[str, object]:
        try:
            return {"available": True, "results": await client.search_pull_requests(project, query)}
        except httpx.HTTPError as e:
            return {"available": False, "reason": f"PR search failed: {e}", "results": []}

    wi, prs, code = await asyncio.gather(
        work_items(), pull_requests(), codesearch.code_search.search(project, query, client)
    )
    return {"query": query, "workItems": wi, "pullRequests": prs, "code": code}


# -- report builder (4E: UC metric view semantic layer) ---------------------------


class BuilderFilter(BaseModel):
    dimension: str
    values: list[str] = []


class BuilderDefinition(BaseModel):
    dimensions: list[str] = []
    measures: list[str]
    filters: list[BuilderFilter] = []
    limit: int | None = None


class SavedReportBody(BaseModel):
    id: str | None = None
    name: str
    definition: dict  # BuilderDefinition + presentation (chartType) — stored opaquely


@router.get("/reports/builder/meta")
async def builder_meta() -> dict[str, object]:
    return await reportbuilder.builder.meta()


@router.post("/reports/builder/run")
async def builder_run(body: BuilderDefinition) -> dict[str, object]:
    try:
        return await reportbuilder.builder.run(body.model_dump())
    except reportbuilder.ReportDefinitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:300])


@router.get("/reports/saved")
async def saved_reports(request: Request) -> dict[str, object]:
    return {"value": await store.list_reports(user_email(request))}


@router.put("/reports/saved")
async def save_report(request: Request, body: SavedReportBody) -> dict[str, object]:
    import json
    import uuid

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is empty")
    report_id = (body.id or "").strip() or uuid.uuid4().hex[:12]
    try:
        await store.save_report(
            user_email(request), report_id, name, json.dumps(body.definition)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:300])
    return {"id": report_id, "name": name}


@router.delete("/reports/saved/{report_id}")
async def delete_report(request: Request, report_id: str) -> dict[str, object]:
    try:
        await store.delete_report(user_email(request), report_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:300])
    return {"ok": True}


@router.get("/projects/{project}/repos/{repo_id}/commits")
async def commits(project: str, repo_id: str, top: int = Query(25, le=100)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_commits(project, repo_id, top=top))}


# -- code browsing ----------------------------------------------------------------


@router.get("/projects/{project}/repos/{repo_id}/branches")
async def branches(project: str, repo_id: str) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_branches(project, repo_id))}


@router.get("/projects/{project}/repos/{repo_id}/tree")
async def tree(project: str, repo_id: str, branch: str = Query(...), path: str = Query("/")) -> dict[str, object]:
    return {"value": await _call(lambda c: c.get_tree(project, repo_id, branch, path))}


@router.get("/projects/{project}/repos/{repo_id}/file")
async def file_content(
    project: str, repo_id: str, path: str = Query(..., min_length=1), branch: str = Query(...)
) -> dict[str, object]:
    return await _call(lambda c: c.get_file(project, repo_id, path, version=branch))


# -- pull request review ------------------------------------------------------------


@router.get("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}/files")
async def pr_files(project: str, repo_id: str, pr_id: int) -> dict[str, object]:
    return await _call(lambda c: c.pr_files(project, repo_id, pr_id))


@router.get("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}/diff")
async def pr_diff(
    project: str, repo_id: str, pr_id: int, path: str = Query(..., min_length=1)
) -> dict[str, object]:
    return await _call(lambda c: c.pr_file_diff(project, repo_id, pr_id, path))


@router.get("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}/threads")
async def pr_threads(project: str, repo_id: str, pr_id: int) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_pr_threads(project, repo_id, pr_id))}


class PrThreadBody(BaseModel):
    comment: str
    filePath: str | None = None
    line: int | None = None


@router.post("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}/threads")
async def create_pr_thread(
    project: str, repo_id: str, pr_id: int, body: PrThreadBody
) -> dict[str, object]:
    if not body.comment.strip():
        raise HTTPException(status_code=422, detail="Comment is empty")
    if body.line is not None and not body.filePath:
        raise HTTPException(status_code=422, detail="line requires filePath")
    return await _call(
        lambda c: c.create_pr_thread(
            project, repo_id, pr_id, body.comment.strip(), body.filePath, body.line
        )
    )


# -- identity, settings, audit ----------------------------------------------------


@router.get("/whoami")
async def whoami(request: Request) -> dict[str, object]:
    ident = request_user(request)
    return {**ident, "store": await store.probe()}


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, object]:
    return {"settings": await store.get_settings(user_email(request))}


class SettingBody(BaseModel):
    key: str
    value: str


@router.put("/settings")
async def put_setting(request: Request, body: SettingBody) -> dict[str, object]:
    if not body.key.strip():
        raise HTTPException(status_code=422, detail="key is empty")
    await store.put_setting(user_email(request), body.key.strip(), body.value)
    return {"ok": True}


@router.get("/audit")
async def audit_log(limit: int = Query(50, le=200)) -> dict[str, object]:
    return {"value": await store.recent_audit(limit)}


# -- analytics data freshness ---------------------------------------------------


@router.get("/analytics/freshness")
async def analytics_freshness() -> dict[str, object]:
    return await insights.freshness()


@router.post("/analytics/refresh")
async def analytics_refresh() -> dict[str, object]:
    return await insights.refresh()


# -- genie (NL analytics) -------------------------------------------------------


class GenieAsk(BaseModel):
    question: str
    conversationId: str | None = None


@router.post("/genie/ask")
async def genie_ask(body: GenieAsk) -> dict[str, object]:
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Question is empty")
    try:
        return await genie.ask(q, body.conversationId)
    except genie.GenieNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Genie request failed: {e}")


# -- AI copilot (tool-calling agent) --------------------------------------------


class CopilotTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class CopilotBody(BaseModel):
    project: str
    message: str
    history: list[CopilotTurn] = []


@router.post("/copilot/chat")
async def copilot_chat(body: CopilotBody) -> dict[str, object]:
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=422, detail="Message is empty")
    try:
        return await copilot.chat(
            body.project, msg, [t.model_dump() for t in body.history[-20:]]
        )
    except copilot.CopilotNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Model endpoint returned {e.response.status_code}"
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach the model endpoint")


# -- generic table artifact (copilot/Genie results → xlsx) --------------------------


class TableExportBody(BaseModel):
    name: str = "data"
    columns: list[str]
    rows: list[list[object]]


@router.post("/export/table")
async def export_table(body: TableExportBody):
    from fastapi.responses import Response

    from app import exports

    if not body.columns or len(body.rows) > 5000:
        raise HTTPException(status_code=422, detail="need columns; max 5000 rows")
    data = exports.table_workbook(body.name, body.columns, body.rows)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in body.name)[:40].strip() or "data"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
    )


# -- copilot session history (per-user chat state in the app-state store) ----------


MAX_SESSION_STATE_CHARS = 400_000


class SessionSaveBody(BaseModel):
    id: str | None = None
    project: str
    title: str | None = None
    state: dict  # opaque chat state: {turns: [...], outcomes: {...}} — the UI owns the shape


@router.get("/copilot/sessions")
async def copilot_sessions(request: Request, project: str = Query(...)) -> dict[str, object]:
    return {"value": await store.list_sessions(user_email(request), project)}


@router.get("/copilot/sessions/{session_id}")
async def copilot_session_detail(request: Request, session_id: str) -> dict[str, object]:
    import json

    s = await store.get_session(user_email(request), session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        s["state"] = json.loads(s["state"] or "{}")
    except ValueError:
        s["state"] = {}
    return s


@router.put("/copilot/sessions")
async def copilot_session_save(request: Request, body: SessionSaveBody) -> dict[str, object]:
    import json
    import uuid

    state = json.dumps(body.state)
    if len(state) > MAX_SESSION_STATE_CHARS:
        raise HTTPException(status_code=413, detail="session too large to save")
    session_id = (body.id or "").strip() or uuid.uuid4().hex[:12]
    title = (body.title or "").strip()[:80] or "Untitled chat"
    try:
        await store.save_session(user_email(request), session_id, body.project, title, state)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:300])
    return {"id": session_id, "title": title}


@router.delete("/copilot/sessions/{session_id}")
async def copilot_session_delete(request: Request, session_id: str) -> dict[str, object]:
    try:
        await store.delete_session(user_email(request), session_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:300])
    return {"ok": True}


class SuggestBody(BaseModel):
    project: str
    type: str | None = None
    title: str | None = None
    description: str | None = None


@router.post("/ai/suggest-workitem")
async def ai_suggest_workitem(body: SuggestBody) -> dict[str, object]:
    if not ((body.title or "").strip() or (body.description or "").strip()):
        raise HTTPException(status_code=422, detail="Provide a title or description to draft from")
    try:
        return await ai.suggest_work_item(body.project, body.model_dump(exclude={"project"}))
    except ai.CopilotNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ai.SuggestionParseError as e:
        raise HTTPException(status_code=502, detail=f"Model returned no usable suggestion: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Model endpoint returned {e.response.status_code}"
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach the model endpoint")


class ExplainBody(BaseModel):
    project: str
    repositoryId: str
    path: str
    branch: str


@router.post("/ai/explain-file")
async def ai_explain_file(body: ExplainBody) -> dict[str, object]:
    try:
        return await ai.explain_file(body.project, body.repositoryId, body.path, body.branch)
    except ai.CopilotNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ai.SuggestionParseError as e:
        raise HTTPException(status_code=502, detail=f"Model returned no usable explanation: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code if e.response.status_code == 404 else 502,
            detail=f"Explain failed: upstream returned {e.response.status_code}",
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach Azure DevOps or the model endpoint")


class ReviewBody(BaseModel):
    project: str
    repositoryId: str
    prId: int
    path: str | None = None


@router.post("/ai/review-pr")
async def ai_review_pr(body: ReviewBody) -> dict[str, object]:
    try:
        return await ai.review_pr(body.project, body.repositoryId, body.prId, body.path)
    except ai.CopilotNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ai.SuggestionParseError as e:
        raise HTTPException(status_code=502, detail=f"Model returned no usable review: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code if e.response.status_code == 404 else 502,
            detail=f"Review failed: upstream returned {e.response.status_code}",
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach Azure DevOps or the model endpoint")


# -- writes -------------------------------------------------------------------


class StateBody(BaseModel):
    state: str


# BFF body keys → ADO field reference names (shared by create + update).
_WI_FIELD_MAP = {
    "title": "System.Title",
    "description": "System.Description",
    "assignedTo": "System.AssignedTo",
    "state": "System.State",
    "tags": "System.Tags",
    "iterationPath": "System.IterationPath",
    "areaPath": "System.AreaPath",
}


class WorkItemCreate(BaseModel):
    type: str
    title: str
    description: str | None = None
    assignedTo: str | None = None
    tags: str | None = None  # "a; b"
    iterationPath: str | None = None


class WorkItemUpdate(BaseModel):
    """All optional; only keys the client sent are patched. An explicit empty
    string on assignedTo clears the field (unassign)."""

    title: str | None = None
    description: str | None = None
    assignedTo: str | None = None
    state: str | None = None
    tags: str | None = None
    iterationPath: str | None = None
    areaPath: str | None = None


class CommentBody(BaseModel):
    text: str


class VoteBody(BaseModel):
    vote: int  # 10 approve, 5 approve w/ suggestions, 0 reset, -5 waiting, -10 reject


class PrStatusBody(BaseModel):
    status: str  # "abandoned" | "active"


@router.post("/projects/{project}/workitems")
async def create_work_item(project: str, body: WorkItemCreate) -> dict[str, object]:
    if not body.type.strip() or not body.title.strip():
        raise HTTPException(status_code=422, detail="type and title are required")
    fields = {
        _WI_FIELD_MAP[k]: v
        for k, v in body.model_dump(exclude={"type"}, exclude_none=True).items()
        if str(v).strip()
    }
    return await _call(lambda c: c.create_work_item(project, body.type.strip(), fields))


@router.patch("/projects/{project}/workitems/{wid}")
async def update_work_item(project: str, wid: int, body: WorkItemUpdate) -> dict[str, object]:
    sent = body.model_dump(exclude_unset=True)
    # Empty assignedTo → clear the field (None becomes a JSON-Patch remove op).
    fields = {
        _WI_FIELD_MAP[k]: (None if k == "assignedTo" and not str(v or "").strip() else v)
        for k, v in sent.items()
    }
    if not fields:
        raise HTTPException(status_code=422, detail="no fields to update")
    await _call(lambda c: c.update_work_item(wid, fields))
    return await _call(lambda c: c.get_work_item(wid))


@router.patch("/projects/{project}/workitems/{wid}/state")
async def set_work_item_state(project: str, wid: int, body: StateBody) -> dict[str, object]:
    return await _call(lambda c: c.update_work_item(wid, {"System.State": body.state}))


@router.post("/projects/{project}/workitems/{wid}/comments")
async def comment_work_item(project: str, wid: int, body: CommentBody) -> dict[str, object]:
    return await _call(lambda c: c.add_work_item_comment(project, wid, body.text))


@router.put("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}/vote")
async def vote_pull_request(
    project: str, repo_id: str, pr_id: int, body: VoteBody
) -> dict[str, object]:
    me = await _call(lambda c: c.connection_data())
    reviewer_id = me.get("id")
    if not reviewer_id:
        raise HTTPException(status_code=502, detail="Could not resolve current user")
    return await _call(lambda c: c.set_pr_vote(project, repo_id, pr_id, reviewer_id, body.vote))


@router.patch("/projects/{project}/repos/{repo_id}/pullrequests/{pr_id}")
async def set_pull_request_status(
    project: str, repo_id: str, pr_id: int, body: PrStatusBody
) -> dict[str, object]:
    return await _call(lambda c: c.set_pr_status(project, repo_id, pr_id, body.status))
