"""App-state store: per-user settings + audit log, in Delta via the SQL warehouse.

Design notes
- Tables live in {store_catalog}.{store_schema} (default workspace.ado_companion_app).
  The schema itself is created by a HUMAN (grant + create, see AGENTS.md §4A); the app
  creates its tables inside it on first use.
- All SQL uses named statement parameters — never string interpolation of values.
- Writes are low-volume. Audit events are buffered in memory and flushed as one
  multi-row INSERT (max ~3s latency) to avoid a warehouse round-trip per click.
- Everything degrades gracefully: if the schema/grants are missing, the store marks
  itself unavailable (with the reason) and all operations become no-ops.
"""
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import anyio

from app.config import settings
from app.genie import _workspace_client

log = logging.getLogger(__name__)

FLUSH_SECS = 3.0
FLUSH_MAX = 25
RETRY_SECS = 120.0  # re-probe an unavailable store (grants may have landed since)


def _fq() -> str:
    return f"{settings.store_catalog}.{settings.store_schema}"


class Store:
    def __init__(self) -> None:
        self._ready: bool | None = None  # None = not yet checked
        self._reason: str | None = None
        self._checked_at = 0.0
        self._init_lock = threading.Lock()
        self._buffer: list[tuple[str, str, str, str, int, str]] = []
        self._buf_lock = threading.Lock()
        self._flush_scheduled = False

    # -- plumbing ---------------------------------------------------------------

    def _exec(self, statement: str, params: dict[str, Any] | None = None) -> Any:
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        w = _workspace_client()
        warehouse = next(iter(w.warehouses.list()), None)
        if warehouse is None:
            raise RuntimeError("no SQL warehouse visible to the app")
        p = [
            StatementParameterListItem(name=k, value=str(v) if v is not None else None,
                                       type="STRING")
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
        # Failure is not forever: grants often land after first boot — re-probe.
        if self._ready is False and time.monotonic() - self._checked_at > RETRY_SECS:
            self._ready = None
        if self._ready is not None:
            return self._ready
        with self._init_lock:
            if self._ready is not None:
                return self._ready
            try:
                fq = _fq()
                self._exec(
                    f"CREATE TABLE IF NOT EXISTS {fq}.settings ("
                    "user_email STRING, key STRING, value STRING, updated_at TIMESTAMP)"
                )
                self._exec(
                    f"CREATE TABLE IF NOT EXISTS {fq}.audit_log ("
                    "ts TIMESTAMP, user_email STRING, action STRING, method STRING, "
                    "path STRING, status INT, detail STRING)"
                )
                self._ready = True
            except Exception as e:
                self._ready, self._reason = False, str(e)[:300]
                self._checked_at = time.monotonic()
                log.warning("app-state store unavailable (will retry): %s", self._reason)
        return self._ready

    def status(self) -> dict[str, Any]:
        if self._ready is None:
            return {"available": None, "reason": "not yet used"}
        return {"available": self._ready, "reason": self._reason}

    # -- settings ---------------------------------------------------------------

    def _get_settings(self, user: str) -> dict[str, str]:
        if not self._ensure():
            return {}
        r = self._exec(
            f"SELECT key, value FROM {_fq()}.settings WHERE user_email = :user",
            {"user": user},
        )
        rows = (r.result.data_array or []) if r.result else []
        return {row[0]: row[1] for row in rows}

    def _put_setting(self, user: str, key: str, value: str) -> None:
        if not self._ensure():
            return
        self._exec(
            f"""MERGE INTO {_fq()}.settings s
                USING (SELECT :user AS u, :key AS k, :value AS v) x
                ON s.user_email = x.u AND s.key = x.k
                WHEN MATCHED THEN UPDATE SET value = x.v, updated_at = current_timestamp()
                WHEN NOT MATCHED THEN INSERT (user_email, key, value, updated_at)
                     VALUES (x.u, x.k, x.v, current_timestamp())""",
            {"user": user, "key": key, "value": value},
        )

    async def get_settings(self, user: str) -> dict[str, str]:
        return await anyio.to_thread.run_sync(self._get_settings, user)

    async def put_setting(self, user: str, key: str, value: str) -> None:
        await anyio.to_thread.run_sync(self._put_setting, user, key, value)

    # -- audit ------------------------------------------------------------------

    def audit(self, user: str, action: str, method: str, path: str, status: int, detail: str) -> None:
        """Queue an audit event (non-blocking); flushed in batches."""
        ts = datetime.now(timezone.utc).isoformat()
        with self._buf_lock:
            self._buffer.append((ts, user, action, method, path, status, detail[:500]))
            need_flush = len(self._buffer) >= FLUSH_MAX
            schedule = not self._flush_scheduled
            if schedule:
                self._flush_scheduled = True
        if need_flush:
            self._kick_flush(0)
        elif schedule:
            self._kick_flush(FLUSH_SECS)

    def _kick_flush(self, delay: float) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(delay, lambda: asyncio.ensure_future(self._flush_async()))
        except RuntimeError:  # no loop (tests/shutdown) — flush inline
            self._flush_sync()

    async def _flush_async(self) -> None:
        await anyio.to_thread.run_sync(self._flush_sync)

    def _flush_sync(self) -> None:
        with self._buf_lock:
            batch, self._buffer = self._buffer, []
            self._flush_scheduled = False
        if not batch or not self._ensure():
            return
        try:
            values, params = [], {}
            for i, (ts, user, action, method, path, status, detail) in enumerate(batch):
                values.append(
                    f"(CAST(:ts{i} AS TIMESTAMP), :u{i}, :a{i}, :m{i}, :p{i}, CAST(:s{i} AS INT), :d{i})"
                )
                params.update({f"ts{i}": ts, f"u{i}": user, f"a{i}": action, f"m{i}": method,
                               f"p{i}": path, f"s{i}": status, f"d{i}": detail})
            self._exec(
                f"INSERT INTO {_fq()}.audit_log (ts, user_email, action, method, path, status, detail) "
                f"VALUES {', '.join(values)}",
                params,
            )
        except Exception as e:
            log.warning("audit flush failed (%d events dropped): %s", len(batch), e)

    def _recent_audit(self, limit: int) -> list[dict[str, Any]]:
        if not self._ensure():
            return []
        r = self._exec(
            f"SELECT CAST(ts AS STRING), user_email, action, method, path, status, detail "
            f"FROM {_fq()}.audit_log ORDER BY ts DESC LIMIT {int(limit)}"
        )
        rows = (r.result.data_array or []) if r.result else []
        keys = ["ts", "user", "action", "method", "path", "status", "detail"]
        return [dict(zip(keys, row)) for row in rows]

    async def recent_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        return await anyio.to_thread.run_sync(self._recent_audit, limit)


store = Store()
