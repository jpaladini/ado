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


def business_days_between(start: date, end: date) -> int:
    """Weekdays strictly after `start`, up to and including `end` (numpy
    busday_count semantics, Mon–Fri only). ADO Analytics' CycleTimeDays /
    LeadTimeDays count calendar days — analysts on a 5-day week want this
    instead. Holidays are intentionally out of scope for v1."""
    if end <= start:
        return 0
    days = (end - start).days
    full_weeks, rem = divmod(days, 7)
    count = full_weeks * 5
    dow = start.weekday()
    for i in range(1, rem + 1):
        if (dow + i) % 7 < 5:  # Mon..Fri
            count += 1
    return count


def _to_date(iso: Any) -> date | None:
    try:
        return date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


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

    # -- 4C report queries (all server-side $apply, all filterable) -----------------

    async def _select(self, project: str, entity: str, params: dict[str, str]) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        path = f"/{proj}/_odata/{ODATA_VERSION}/{entity}"
        async with self._client() as client:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json().get("value", [])

    @staticmethod
    def _filters(
        types: list[str] | None, assignees: list[str] | None, extra: list[str] | None = None
    ) -> str:
        """AND-combined OData filter clauses (values single-quote escaped)."""
        def esc(v: str) -> str:
            return v.replace("'", "''")

        clauses = list(extra or [])
        if types:
            ors = " or ".join(f"WorkItemType eq '{esc(t)}'" for t in types)
            clauses.append(f"({ors})")
        if assignees:
            ors = " or ".join(f"AssignedTo/UserName eq '{esc(a)}'" for a in assignees)
            clauses.append(f"({ors})")
        return " and ".join(clauses)

    async def created_per_day(
        self, project: str, days: int, types: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        f = self._filters(types, assignees, [f"CreatedDateSK ge {start}"])
        rows = await self._odata(
            project, "WorkItems", f"filter({f})/groupby((CreatedDateSK),aggregate($count as Count))"
        )
        return sorted(
            ({"dateSK": int(r["CreatedDateSK"]), "count": int(r.get("Count", 0))}
             for r in rows if r.get("CreatedDateSK")),
            key=lambda r: r["dateSK"],
        )

    async def completed_per_day(
        self, project: str, days: int, types: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        f = self._filters(types, assignees,
                          [f"ClosedDateSK ge {start}", "StateCategory eq 'Completed'"])
        rows = await self._odata(
            project, "WorkItems", f"filter({f})/groupby((ClosedDateSK),aggregate($count as Count))"
        )
        return sorted(
            ({"dateSK": int(r["ClosedDateSK"]), "count": int(r.get("Count", 0))}
             for r in rows if r.get("ClosedDateSK")),
            key=lambda r: r["dateSK"],
        )

    async def cycle_time_items(
        self, project: str, days: int, types: list[str] | None = None,
        assignees: list[str] | None = None, top: int = 500,
    ) -> list[dict[str, Any]]:
        """One dot per completed item: close date + cycle/lead time (server-computed)."""
        start = (date.today() - timedelta(days=days)).isoformat()
        f = self._filters(types, assignees,
                          [f"ClosedDate ge {start}Z", "StateCategory eq 'Completed'"])
        rows = await self._select(
            project, "WorkItems",
            {
                "$filter": f,
                "$select": "WorkItemId,Title,WorkItemType,CycleTimeDays,LeadTimeDays,"
                           "CreatedDate,ActivatedDate,ClosedDate",
                "$top": str(top),
            },
        )
        out = []
        for r in rows:
            created = _to_date(r.get("CreatedDate"))
            activated = _to_date(r.get("ActivatedDate")) or created
            closed = _to_date(r.get("ClosedDate"))
            out.append(
                {
                    "id": r.get("WorkItemId"),
                    "title": r.get("Title"),
                    "type": r.get("WorkItemType"),
                    # calendar-day values as ADO computes them (kept for reference)
                    "cycleDays": float(r.get("CycleTimeDays") or 0),
                    "leadDays": float(r.get("LeadTimeDays") or 0),
                    # 5-day-workweek values (what the charts and KPIs use)
                    "cycleBdays": business_days_between(activated, closed) if activated and closed else 0,
                    "leadBdays": business_days_between(created, closed) if created and closed else 0,
                    "closedDate": str(r.get("ClosedDate"))[:10],
                }
            )
        return out

    async def cfd(
        self, project: str, days: int, types: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Cumulative-flow input: daily counts per StateCategory from snapshots."""
        start = (date.today() - timedelta(days=max(days - 1, 0))).isoformat()
        f = self._filters(types, assignees,
                          [f"DateValue ge {start}Z", "StateCategory ne 'Removed'"])
        rows = await self._odata(
            project, "WorkItemSnapshot",
            f"filter({f})/groupby((DateValue,StateCategory),aggregate($count as Count))",
        )
        out = [
            {"date": str(r.get("DateValue"))[:10],
             "category": r.get("StateCategory") or "Unknown",
             "count": int(r.get("Count", 0))}
            for r in rows
        ]
        out.sort(key=lambda r: (r["date"], r["category"]))
        return out

    async def open_items_detail(
        self, project: str, types: list[str] | None = None,
        assignees: list[str] | None = None, top: int = 500,
    ) -> list[dict[str, Any]]:
        """Open items with created date + state — feeds aging-WIP and workload."""
        f = self._filters(types, assignees,
                          ["StateCategory ne 'Completed'", "StateCategory ne 'Removed'"])
        rows = await self._select(
            project, "WorkItems",
            {
                "$filter": f,
                "$select": "WorkItemId,Title,WorkItemType,State,StateCategory,CreatedDate",
                "$expand": "AssignedTo($select=UserName)",
                "$top": str(top),
            },
        )
        out = []
        for r in rows:
            created = _to_date(r.get("CreatedDate"))
            age = (date.today() - created).days if created else 0
            age_bd = business_days_between(created, date.today()) if created else 0
            out.append(
                {
                    "id": r.get("WorkItemId"),
                    "title": r.get("Title"),
                    "type": r.get("WorkItemType"),
                    "state": r.get("State"),
                    "category": r.get("StateCategory"),
                    "assignee": (r.get("AssignedTo") or {}).get("UserName"),
                    "ageDays": age,
                    "ageBdays": age_bd,
                }
            )
        return out
