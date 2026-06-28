"""API routes — the BFF surface the React app calls."""
import httpx
from fastapi import APIRouter, HTTPException

from app.ado.client import ADOClient, ADOConfigError
from app.config import settings

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "ado_configured": settings.ado_configured}


@router.get("/me")
async def me() -> dict[str, object]:
    try:
        client = ADOClient()
        return await client.connection_data()
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="ADO request failed")


@router.get("/projects")
async def projects() -> dict[str, object]:
    try:
        client = ADOClient()
        return {"value": await client.list_projects()}
    except ADOConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="ADO request failed")
