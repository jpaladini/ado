"""Freshness + refresh: mocked workspace client, every degradation branch."""
import app.insights as insights


class _State:
    def __init__(self, value):
        self.state = value


class _Status:
    def __init__(self, ok=True, msg=None):
        from databricks.sdk.service.sql import StatementState

        self.state = StatementState.SUCCEEDED if ok else StatementState.FAILED
        self.error = type("E", (), {"message": msg})() if msg else None


def _stmt_result(rows, cols=None, ok=True, msg=None):
    r = type("R", (), {})()
    r.status = _Status(ok=ok, msg=msg)
    r.result = type("D", (), {"data_array": rows})()
    if cols is not None:
        col_objs = [type("C", (), {"name": c})() for c in cols]
        r.manifest = type("M", (), {"schema": type("S", (), {"columns": col_objs})()})()
    else:
        r.manifest = None
    return r


class _Warehouses:
    def __init__(self, items):
        self._items = items

    def list(self):
        return iter(self._items)


class _Exec:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def execute_statement(self, **kw):
        self.calls.append(kw["statement"])
        return self._results.pop(0)


def _client(results, warehouses=({"id": "w1"},)):
    w = type("W", (), {})()
    w.warehouses = _Warehouses([type("Wh", (), wh)() for wh in warehouses])
    w.statement_execution = _Exec(results)
    return w


def test_freshness_happy_path(monkeypatch):
    results = [
        _stmt_result([["2026-07-03"]]),
        _stmt_result([["x", "2026-07-03 05:04:00"]], cols=["name", "lastModified"]),
    ]
    monkeypatch.setattr(insights, "_workspace_client", lambda: _client(results))
    out = insights._freshness_sync()
    assert out == {"available": True, "asOf": "2026-07-03", "updatedAt": "2026-07-03 05:04:00"}


def test_freshness_without_last_modified_column(monkeypatch):
    results = [
        _stmt_result([["2026-07-03"]]),
        _stmt_result([["x"]], cols=["name"]),  # DESCRIBE DETAIL lacks lastModified
    ]
    monkeypatch.setattr(insights, "_workspace_client", lambda: _client(results))
    out = insights._freshness_sync()
    assert out["available"] is True and out["updatedAt"] is None


def test_freshness_no_warehouse(monkeypatch):
    monkeypatch.setattr(insights, "_workspace_client", lambda: _client([], warehouses=()))
    out = insights._freshness_sync()
    assert out["available"] is False and "warehouse" in out["reason"]


def test_freshness_query_failure(monkeypatch):
    results = [_stmt_result([], ok=False, msg="TABLE_OR_VIEW_NOT_FOUND")]
    monkeypatch.setattr(insights, "_workspace_client", lambda: _client(results))
    out = insights._freshness_sync()
    assert out["available"] is False and "TABLE_OR_VIEW_NOT_FOUND" in out["reason"]


def _jobs_client(jobs, run_id=42):
    w = type("W", (), {})()

    class _Jobs:
        def list(self):
            return iter(
                type("J", (), {"job_id": jid, "settings": type("S", (), {"name": name})()})()
                for jid, name in jobs
            )

        def run_now(self, job_id):
            w.ran = job_id
            return type("Wait", (), {"run_id": run_id, "response": None})()

    w.jobs = _Jobs()
    return w


def test_refresh_finds_job_by_suffix(monkeypatch):
    w = _jobs_client([(1, "other"), (7, "dev-ado-analytics-ingest")])
    monkeypatch.setattr(insights, "_workspace_client", lambda: w)
    out = insights._refresh_sync()
    assert out == {"started": True, "runId": 42} and w.ran == 7


def test_refresh_job_not_visible(monkeypatch):
    monkeypatch.setattr(insights, "_workspace_client", lambda: _jobs_client([(1, "other")]))
    out = insights._refresh_sync()
    assert out["started"] is False and "not visible" in out["reason"]
