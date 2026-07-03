"""App-state store internals: settings, audit buffering/flush, re-probe."""
import time

import pytest

from app.store import FLUSH_MAX, Store


class _R:
    def __init__(self, rows=None):
        self.result = type("D", (), {"data_array": rows or []})()


def _store(monkeypatch, rows=None, fail=False):
    s = Store()
    s._ready = True
    calls = []

    def fake_exec(sql, params=None):
        calls.append((sql, params))
        if fail:
            raise RuntimeError("warehouse down")
        return _R(rows)

    monkeypatch.setattr(s, "_exec", fake_exec)
    return s, calls


def test_settings_roundtrip(monkeypatch):
    s, calls = _store(monkeypatch, rows=[["theme", "dark"], ["density", "cozy"]])
    assert s._get_settings("u@x.com") == {"theme": "dark", "density": "cozy"}

    s._put_setting("u@x.com", "theme", "light")
    sql, params = calls[-1]
    assert "MERGE INTO" in sql and params == {"user": "u@x.com", "key": "theme", "value": "light"}


def test_settings_degrade_to_empty(monkeypatch):
    s = Store()
    monkeypatch.setattr(s, "_ensure", lambda: False)
    assert s._get_settings("u@x.com") == {}
    s._put_setting("u@x.com", "k", "v")  # silently a no-op, must not raise


def test_audit_buffers_then_flushes_one_insert(monkeypatch):
    s, calls = _store(monkeypatch)
    for i in range(3):
        with s._buf_lock:  # enqueue directly; the async kick needs a loop
            s._buffer.append((f"t{i}", "u", "a", "GET", "/p", 200, "d"))
    s._flush_sync()
    assert len(calls) == 1  # one multi-row INSERT, not one per event
    sql, params = calls[0]
    assert sql.count("(CAST(") == 3 and params["u0"] == "u" and params["p2"] == "/p"
    assert s._buffer == []  # drained


def test_audit_flush_failure_drops_batch_quietly(monkeypatch):
    s, _ = _store(monkeypatch, fail=True)
    with s._buf_lock:
        s._buffer.append(("t", "u", "a", "GET", "/p", 200, "d"))
    s._flush_sync()  # must swallow the error (audit never breaks requests)
    assert s._buffer == []


def test_audit_kicks_inline_without_event_loop(monkeypatch):
    # No running loop (tests/shutdown) → each event flushes synchronously,
    # so nothing is ever stranded in the buffer.
    s, calls = _store(monkeypatch)
    s.audit("u@x.com", "a", "GET", "/p", 200, "detail")
    assert len(calls) == 1 and s._buffer == []
    assert calls[0][1]["u0"] == "u@x.com"
    assert s.status() == {"available": True, "reason": None}


def test_recent_audit_maps_rows(monkeypatch):
    s, _ = _store(monkeypatch, rows=[["2026-07-03", "u", "a", "GET", "/p", 200, "d"]])
    out = s._recent_audit(5)
    assert out == [{"ts": "2026-07-03", "user": "u", "action": "a", "method": "GET",
                    "path": "/p", "status": 200, "detail": "d"}]


def test_ensure_reprobes_after_retry_window(monkeypatch):
    s = Store()
    s._ready = False
    s._reason = "grants missing"
    s._checked_at = time.monotonic() - 999  # past RETRY_SECS

    created = []

    def fake_exec(sql, params=None):
        created.append(sql)
        return _R()

    monkeypatch.setattr(s, "_exec", fake_exec)
    assert s._ensure() is True  # failure was not cached forever
    assert any("settings" in c for c in created)
    assert any("ai_sessions" in c for c in created)
    assert any("saved_reports" in c for c in created)


@pytest.mark.asyncio
async def test_async_wrappers_delegate(monkeypatch):
    s, _ = _store(monkeypatch, rows=[["k", "v"]])
    assert await s.get_settings("u@x.com") == {"k": "v"}
    await s.put_setting("u@x.com", "k", "v2")
    out = await s.recent_audit(1)
    assert out and out[0]["ts"] == "k"  # same fake row, mapped through audit keys
