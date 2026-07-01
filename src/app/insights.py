"""Freshness + on-demand refresh for the analytics Delta tables.

The Genie tables are a batch copy of ADO Analytics (see jobs/ingest_ado_analytics.py),
refreshed on the job's schedule — so answers can lag the live CRUD tabs. This module
lets the UI (a) show how fresh the data is and (b) kick the ingest job on demand.

Both degrade gracefully: if the app's service principal can't see the warehouse or the
job (grants are the human's call), the endpoints report unavailable instead of failing.
"""
import logging
from typing import Any

import anyio

from app.config import settings
from app.genie import _workspace_client

log = logging.getLogger(__name__)

JOB_SUFFIX = "ado-analytics-ingest"


def _fq() -> str:
    return f"{settings.analytics_catalog}.{settings.analytics_schema}"


def _freshness_sync() -> dict[str, Any]:
    from databricks.sdk.service.sql import StatementState

    try:
        w = _workspace_client()
        warehouse = next(iter(w.warehouses.list()), None)
        if warehouse is None:
            return {"available": False, "reason": "no SQL warehouse visible to the app"}
        r = w.statement_execution.execute_statement(
            statement=f"SELECT CAST(max(`date`) AS STRING) FROM {_fq()}.work_item_daily",
            warehouse_id=warehouse.id,
            wait_timeout="30s",
        )
        if r.status and r.status.state == StatementState.SUCCEEDED and r.result and r.result.data_array:
            return {"available": True, "asOf": r.result.data_array[0][0]}
        detail = (r.status.error.message if r.status and r.status.error else None) or "query did not succeed"
        return {"available": False, "reason": detail[:200]}
    except Exception as e:
        log.info("freshness check failed: %s", e)
        return {"available": False, "reason": str(e)[:200]}


def _refresh_sync() -> dict[str, Any]:
    try:
        w = _workspace_client()
        job_id = None
        for j in w.jobs.list():
            if (j.settings.name or "").endswith(JOB_SUFFIX):
                job_id = j.job_id
                break
        if job_id is None:
            return {"started": False, "reason": "ingest job not visible to the app (grant CAN_MANAGE_RUN)"}
        wait = w.jobs.run_now(job_id=job_id)
        run_id = getattr(wait, "run_id", None) or (wait.response.run_id if wait.response else None)
        return {"started": True, "runId": run_id}
    except Exception as e:
        log.info("refresh trigger failed: %s", e)
        return {"started": False, "reason": str(e)[:200]}


async def freshness() -> dict[str, Any]:
    return await anyio.to_thread.run_sync(_freshness_sync)


async def refresh() -> dict[str, Any]:
    return await anyio.to_thread.run_sync(_refresh_sync)
