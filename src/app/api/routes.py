"""API routes — the BFF surface the React app calls."""
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import APIRouter, HTTPException, Query

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


@router.get("/projects/{project}/repos/{repo_id}/commits")
async def commits(project: str, repo_id: str, top: int = Query(25, le=100)) -> dict[str, object]:
    return {"value": await _call(lambda c: c.list_commits(project, repo_id, top=top))}
