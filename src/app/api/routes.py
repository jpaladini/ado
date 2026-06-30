"""API routes — the BFF surface the React app calls."""
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.ado.analytics import AnalyticsClient, OPEN_CATEGORIES
from app.ado.client import ADOClient, ADOConfigError
from app.config import settings

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
    return {"status": "ok", "ado_configured": settings.ado_configured}


@router.get("/me")
async def me() -> dict[str, object]:
    return await _call(lambda c: c.connection_data())


@router.get("/projects")
async def projects() -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_projects())}


@router.get("/projects/{project}/workitems")
async def work_items(project: str, top: int = Query(100, le=200)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_work_items(project, top=top))}


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


# -- writes -------------------------------------------------------------------


class StateBody(BaseModel):
    state: str


class CommentBody(BaseModel):
    text: str


class VoteBody(BaseModel):
    vote: int  # 10 approve, 5 approve w/ suggestions, 0 reset, -5 waiting, -10 reject


class PrStatusBody(BaseModel):
    status: str  # "abandoned" | "active"


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
