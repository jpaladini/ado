"""API routes — the BFF surface the React app calls."""
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app import ai, copilot, genie, insights
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


@router.get("/projects/{project}/repos/{repo_id}/commits")
async def commits(project: str, repo_id: str, top: int = Query(25, le=100)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_commits(project, repo_id, top=top))}


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
