"""Thin async client for the Azure DevOps REST API.

This is the *operational* data plane — it talks to the live ADO API. No ADO data
is persisted locally. Auth is PAT-based (Basic auth with an empty username), which
mirrors the original mobile app; corporate will swap this for Entra OAuth.
"""
import base64
from typing import Any

import httpx

from app.config import settings

API_VERSION = "7.1"


class ADOConfigError(RuntimeError):
    """Raised when the ADO org URL / PAT are not configured."""


def _auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {token}"


class ADOClient:
    def __init__(self, org_url: str | None = None, pat: str | None = None) -> None:
        self.org_url = (org_url or settings.ado_org_url).rstrip("/")
        self.pat = pat or settings.ado_pat
        if not self.org_url or not self.pat:
            raise ADOConfigError("ADO_ORG_URL and ADO_PAT must be set")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.org_url,
            headers={"Authorization": _auth_header(self.pat), "Accept": "application/json"},
            timeout=20.0,
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"api-version": API_VERSION, **(params or {})}
        async with self._client() as client:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()

    async def list_projects(self) -> list[dict[str, Any]]:
        """GET /_apis/projects"""
        data = await self._get("/_apis/projects")
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description", ""),
                "lastUpdateTime": p.get("lastUpdateTime"),
                "state": p.get("state"),
            }
            for p in data.get("value", [])
        ]

    async def connection_data(self) -> dict[str, Any]:
        """Authenticated user info via /_apis/connectionData."""
        data = await self._get("/_apis/connectionData")
        user = data.get("authenticatedUser", {})
        return {
            "id": user.get("id"),
            "displayName": user.get("providerDisplayName") or user.get("customDisplayName"),
        }
