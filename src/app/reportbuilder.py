"""Report builder (4E): a governed semantic layer + a tiny query planner.

The semantic layer is a Unity Catalog **metric view** — measures and dimensions
defined once in YAML, versioned with this file, visible to Genie and any other
UC-aware tool. The app creates/refreshes the view lazily in its own app-state
schema (where it holds CREATE TABLE) over the ingested analytics Delta table
(where it holds SELECT). Queries are `SELECT dims…, MEASURE(measure)…` — the
builder UI picks dimensions × measures × chart type and the app draws the rows
with the same Observable Plot components as the curated widgets.

Batch-plane caveat: the source is the ingest job's Delta copy, so builder
reports are historical (refreshed on the job's schedule) — the curated Reports
widgets stay near-live OData.

Durations are 5-day-workweek business days, same unit as everywhere else. The
SQL closed form below is verified equal to analytics.business_days_between for
all date pairs (weekdays strictly after start, through end inclusive).
"""
import logging
import threading
import time
from typing import Any

import anyio

from app.config import settings
from app.genie import _workspace_client

log = logging.getLogger(__name__)

RETRY_SECS = 120.0  # re-probe an unavailable builder (grants may land later)
MAX_ROWS = 1000
DEFAULT_ROWS = 500

# Weekdays from a fixed epoch Monday (1970-01-05) through {d} inclusive.
_WEEKDAYS_THROUGH = (
    "5*(datediff({d}, DATE'1970-01-05') DIV 7)"
    " + LEAST(datediff({d}, DATE'1970-01-05') % 7 + 1, 5)"
)
# Business days created→completed (NULL while open, so AVG/PERCENTILE skip them).
_LEAD_BDAYS = (
    "CASE WHEN completed_date IS NOT NULL THEN GREATEST(0, "
    + _WEEKDAYS_THROUGH.format(d="CAST(completed_date AS DATE)")
    + " - ("
    + _WEEKDAYS_THROUGH.format(d="CAST(created_date AS DATE)")
    + ")) END"
)

# The semantic layer. `name` is both the YAML identity and the result column;
# labels/kinds are UI metadata. kind: category → chip filterable + bar charts;
# date → time-axis charts.
DIMENSIONS: list[dict[str, str]] = [
    {"name": "type", "label": "Type", "kind": "category", "expr": "type"},
    {"name": "state", "label": "State", "kind": "category", "expr": "state"},
    {"name": "state_category", "label": "State category", "kind": "category",
     "expr": "state_category"},
    {"name": "assignee", "label": "Assignee", "kind": "category",
     "expr": "COALESCE(assigned_to, 'Unassigned')"},
    {"name": "created_day", "label": "Created (day)", "kind": "date",
     "expr": "CAST(created_date AS DATE)"},
    {"name": "created_week", "label": "Created (week)", "kind": "date",
     "expr": "CAST(DATE_TRUNC('WEEK', created_date) AS DATE)"},
    {"name": "created_month", "label": "Created (month)", "kind": "date",
     "expr": "CAST(DATE_TRUNC('MONTH', created_date) AS DATE)"},
    {"name": "completed_day", "label": "Completed (day)", "kind": "date",
     "expr": "CAST(completed_date AS DATE)"},
    {"name": "completed_week", "label": "Completed (week)", "kind": "date",
     "expr": "CAST(DATE_TRUNC('WEEK', completed_date) AS DATE)"},
    {"name": "completed_month", "label": "Completed (month)", "kind": "date",
     "expr": "CAST(DATE_TRUNC('MONTH', completed_date) AS DATE)"},
]

MEASURES: list[dict[str, str]] = [
    {"name": "items", "label": "Items", "format": "int", "expr": "COUNT(1)"},
    {"name": "completed_items", "label": "Completed items", "format": "int",
     "expr": "COUNT(completed_date)"},
    {"name": "open_items", "label": "Open items", "format": "int",
     "expr": "COUNT_IF(completed_date IS NULL)"},
    {"name": "avg_lead_bdays", "label": "Avg lead time (bdays)", "format": "days",
     "expr": f"ROUND(AVG({_LEAD_BDAYS}), 1)"},
    {"name": "lead_p50_bdays", "label": "Lead time p50 (bdays)", "format": "days",
     "expr": f"PERCENTILE({_LEAD_BDAYS}, 0.5)"},
    {"name": "lead_p85_bdays", "label": "Lead time p85 (bdays)", "format": "days",
     "expr": f"PERCENTILE({_LEAD_BDAYS}, 0.85)"},
]

_DIM_BY_NAME = {d["name"]: d for d in DIMENSIONS}
_MEASURE_BY_NAME = {m["name"]: m for m in MEASURES}


def _source_fq() -> str:
    return f"{settings.analytics_catalog}.{settings.analytics_schema}.work_items"


def view_fq() -> str:
    return f"{settings.store_catalog}.{settings.store_schema}.work_items_metrics"


def metric_view_yaml() -> str:
    """The metric view definition — YAML lives in code so it's versioned/reviewed."""
    lines = ["version: 0.1", f"source: {_source_fq()}", "dimensions:"]
    for d in DIMENSIONS:
        lines += [f"  - name: {d['name']}", f"    expr: {d['expr']}"]
    lines.append("measures:")
    for m in MEASURES:
        lines += [f"  - name: {m['name']}", f"    expr: {m['expr']}"]
    return "\n".join(lines)


def metric_view_ddl() -> str:
    return (
        f"CREATE OR REPLACE VIEW {view_fq()}\n"
        "WITH METRICS\nLANGUAGE YAML\nAS $$\n" + metric_view_yaml() + "\n$$"
    )


class ReportDefinitionError(ValueError):
    """A builder definition referenced unknown dimensions/measures."""


def build_query(definition: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Definition → (SQL over the metric view, named parameters).

    Everything structural (identifiers, exprs) comes from the registries above —
    user input only selects registry names; filter *values* are bound parameters.
    """
    dims = list(dict.fromkeys(definition.get("dimensions") or []))
    measures = list(dict.fromkeys(definition.get("measures") or []))
    if not measures:
        raise ReportDefinitionError("pick at least one measure")
    if len(dims) > 2:
        raise ReportDefinitionError("at most two dimensions")
    unknown = [d for d in dims if d not in _DIM_BY_NAME]
    unknown += [m for m in measures if m not in _MEASURE_BY_NAME]
    if unknown:
        raise ReportDefinitionError(f"unknown fields: {', '.join(unknown)}")

    select = [f"`{d}`" for d in dims]
    select += [f"MEASURE(`{m}`) AS `{m}`" for m in measures]

    where, params = [], {}
    for i, f in enumerate(definition.get("filters") or []):
        name = f.get("dimension")
        values = [str(v) for v in (f.get("values") or []) if str(v).strip()]
        if name not in _DIM_BY_NAME:
            raise ReportDefinitionError(f"unknown filter dimension: {name}")
        if not values:
            continue
        marks = []
        for j, v in enumerate(values):
            params[f"f{i}_{j}"] = v
            marks.append(f":f{i}_{j}")
        where.append(f"`{name}` IN ({', '.join(marks)})")

    limit = min(max(int(definition.get("limit") or DEFAULT_ROWS), 1), MAX_ROWS)
    sql = f"SELECT {', '.join(select)} FROM {view_fq()}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if dims:
        sql += f" GROUP BY {', '.join(f'`{d}`' for d in dims)}"
        first = _DIM_BY_NAME[dims[0]]
        # time on a time axis ascending; categories ranked by the first measure
        if first["kind"] == "date":
            sql += f" ORDER BY `{dims[0]}` ASC"
        else:
            sql += f" ORDER BY `{measures[0]}` DESC"
    sql += f" LIMIT {limit}"
    return sql, params


class ReportBuilder:
    """Lazily ensures the metric view exists, then runs builder queries.

    Mirrors the app-state store's degradation contract: if the warehouse or
    grants are missing, meta() reports unavailable (with the reason) and the
    UI hides the builder — nothing else breaks.
    """

    def __init__(self) -> None:
        self._ready: bool | None = None
        self._reason: str | None = None
        self._checked_at = 0.0
        self._lock = threading.Lock()

    def _exec(self, statement: str, params: dict[str, str] | None = None) -> Any:
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        w = _workspace_client()
        warehouse = next(iter(w.warehouses.list()), None)
        if warehouse is None:
            raise RuntimeError("no SQL warehouse visible to the app")
        p = [
            StatementParameterListItem(name=k, value=v, type="STRING")
            for k, v in (params or {}).items()
        ]
        r = w.statement_execution.execute_statement(
            statement=statement, warehouse_id=warehouse.id, wait_timeout="50s",
            parameters=p or None,
        )
        if not (r.status and r.status.state == StatementState.SUCCEEDED):
            msg = (r.status.error.message if r.status and r.status.error else None) or "statement failed"
            raise RuntimeError(msg)
        return r

    def _ensure(self) -> bool:
        if self._ready is False and time.monotonic() - self._checked_at > RETRY_SECS:
            self._ready = None
        if self._ready is not None:
            return self._ready
        with self._lock:
            if self._ready is not None:
                return self._ready
            try:
                self._exec(metric_view_ddl())
                self._ready = True
            except Exception as e:
                self._ready, self._reason = False, str(e)[:300]
                self._checked_at = time.monotonic()
                log.warning("report builder unavailable (will retry): %s", self._reason)
        return self._ready

    def _meta(self) -> dict[str, Any]:
        available = self._ensure()
        meta: dict[str, Any] = {
            "available": available,
            "dimensions": [
                {"name": d["name"], "label": d["label"], "kind": d["kind"]}
                for d in DIMENSIONS
            ],
            "measures": [
                {"name": m["name"], "label": m["label"], "format": m["format"]}
                for m in MEASURES
            ],
            "view": view_fq(),
            "source": _source_fq(),
            "durationUnit": "businessDays",
        }
        if not available:
            meta["reason"] = self._reason
        return meta

    def _run(self, definition: dict[str, Any]) -> dict[str, Any]:
        # validate before the availability probe: a bad definition is the caller's
        # 422 even when the warehouse is down
        sql, params = build_query(definition)
        if not self._ensure():
            raise RuntimeError(self._reason or "report builder unavailable")
        r = self._exec(sql, params)
        cols = (
            [c.name for c in r.manifest.schema.columns]
            if r.manifest and r.manifest.schema and r.manifest.schema.columns
            else []
        )
        raw = (r.result.data_array or []) if r.result else []
        measure_names = set(definition.get("measures") or [])
        rows = []
        for row in raw:
            out: dict[str, Any] = {}
            for name, value in zip(cols, row):
                if name in measure_names and value is not None:
                    out[name] = float(value)
                else:
                    out[name] = value
            rows.append(out)
        return {"columns": cols, "rows": rows}

    async def meta(self) -> dict[str, Any]:
        return await anyio.to_thread.run_sync(self._meta)

    async def run(self, definition: dict[str, Any]) -> dict[str, Any]:
        return await anyio.to_thread.run_sync(self._run, definition)


builder = ReportBuilder()
