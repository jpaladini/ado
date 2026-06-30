"""Azure DevOps **Analytics** (OData) client — the analytical data plane.

Unlike the operational REST client (app/ado/client.py), this hits the Analytics
service host (analytics.dev.azure.com) and lets the *server* aggregate via OData
`$apply` (groupby/aggregate/filter) and daily `WorkItemSnapshot` trends — so we
fetch numbers, not rows. Same PAT auth as the REST client.
"""
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.ado.client import ADOConfigError, _auth_header
from app.config import settings

ODATA_VERSION = "v4.0-preview"

# StateCategory is process-agnostic: Proposed / InProgress / Resolved / Completed / Removed.
OPEN_CATEGORIES = {"Proposed", "InProgress", "Resolved"}


class AnalyticsClient:
    def __init__(self, org_url: str | None = None, pat: str | None = None) -> None:
        org = (org_url or settings.ado_org_url).rstrip("/")
        self.pat = pat or settings.ado_pat
        if not org or not self.pat:
            raise ADOConfigError("ADO_ORG_URL and ADO_PAT must be set")
        # https://dev.azure.com/{org} -> https://analytics.dev.azure.com/{org}
        self.root = org.replace("https://dev.azure.com", "https://analytics.dev.azure.com")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.root,
            headers={"Authorization": _auth_header(self.pat), "Accept": "application/json"},
            timeout=30.0,
        )

    async def _odata(self, project: str, entity: str, apply: str) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        path = f"/{proj}/_odata/{ODATA_VERSION}/{entity}"
        async with self._client() as client:
            resp = await client.get(path, params={"$apply": apply})
            resp.raise_for_status()
            return resp.json().get("value", [])

    async def count_by_state_category(self, project: str) -> dict[str, int]:
        """Server-side count of work items grouped by StateCategory (one small call)."""
        rows = await self._odata(
            project, "WorkItems", "groupby((StateCategory),aggregate($count as Count))"
        )
        return {(r.get("StateCategory") or "Unknown"): int(r.get("Count", 0)) for r in rows}

    async def open_trend(self, project: str, days: int) -> list[dict[str, Any]]:
        """Daily count of *open* work items over the window, via WorkItemSnapshot."""
        start = (date.today() - timedelta(days=max(days - 1, 0))).isoformat()
        apply = (
            f"filter(DateValue ge {start}Z and StateCategory ne 'Completed' "
            f"and StateCategory ne 'Removed')"
            f"/groupby((DateValue),aggregate($count as Count))"
        )
        rows = await self._odata(project, "WorkItemSnapshot", apply)
        out = [{"date": str(r.get("DateValue"))[:10], "count": int(r.get("Count", 0))} for r in rows]
        out.sort(key=lambda r: r["date"])
        return out
