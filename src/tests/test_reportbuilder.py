"""Report builder (4E): query planning, metric-view DDL, saved-report store,
and the SQL business-days closed form's parity with business_days_between."""
from datetime import date, timedelta

import pytest

from app import reportbuilder as rb
from app.ado.analytics import business_days_between
from app.reportbuilder import ReportDefinitionError, build_query
from app.store import Store


# ---- build_query -----------------------------------------------------------------


def test_build_query_dims_and_measures():
    sql, params = build_query({"dimensions": ["type"], "measures": ["items"]})
    assert sql.startswith("SELECT `type`, MEASURE(`items`) AS `items` FROM ")
    assert rb.view_fq() in sql
    assert "GROUP BY `type`" in sql
    assert "ORDER BY `items` DESC" in sql  # categories ranked by first measure
    assert sql.endswith("LIMIT 500")
    assert params == {}


def test_build_query_date_dim_orders_ascending():
    sql, _ = build_query({"dimensions": ["created_month"], "measures": ["items"]})
    assert "ORDER BY `created_month` ASC" in sql


def test_build_query_zero_dims_has_no_group_by():
    sql, _ = build_query({"dimensions": [], "measures": ["items", "open_items"]})
    assert "GROUP BY" not in sql and "ORDER BY" not in sql
    assert "MEASURE(`open_items`) AS `open_items`" in sql


def test_build_query_filters_are_parameterized():
    sql, params = build_query(
        {
            "dimensions": ["state"],
            "measures": ["items"],
            "filters": [{"dimension": "assignee", "values": ["Ada", "Grace"]}],
        }
    )
    assert "WHERE `assignee` IN (:f0_0, :f0_1)" in sql
    assert params == {"f0_0": "Ada", "f0_1": "Grace"}
    # values never appear in the SQL text — injection-shaped input stays a parameter
    sql2, params2 = build_query(
        {
            "dimensions": ["state"],
            "measures": ["items"],
            "filters": [{"dimension": "assignee", "values": ["'; DROP TABLE x --"]}],
        }
    )
    assert "DROP TABLE" not in sql2
    assert params2["f0_0"] == "'; DROP TABLE x --"


def test_build_query_empty_filter_values_skipped():
    sql, params = build_query(
        {
            "dimensions": ["state"],
            "measures": ["items"],
            "filters": [{"dimension": "assignee", "values": ["  ", ""]}],
        }
    )
    assert "WHERE" not in sql and params == {}


def test_build_query_dedupes_and_clamps_limit():
    sql, _ = build_query(
        {"dimensions": ["type", "type"], "measures": ["items", "items"], "limit": 99999}
    )
    assert sql.count("`type`,") == 1
    assert sql.endswith(f"LIMIT {rb.MAX_ROWS}")
    sql_low, _ = build_query({"dimensions": [], "measures": ["items"], "limit": -5})
    assert sql_low.endswith("LIMIT 1")


@pytest.mark.parametrize(
    "definition,fragment",
    [
        ({"dimensions": [], "measures": []}, "at least one measure"),
        ({"dimensions": ["type", "state", "assignee"], "measures": ["items"]}, "at most two"),
        ({"dimensions": ["nope"], "measures": ["items"]}, "unknown fields: nope"),
        ({"dimensions": [], "measures": ["evil()"]}, "unknown fields: evil()"),
        (
            {"dimensions": [], "measures": ["items"], "filters": [{"dimension": "x", "values": ["a"]}]},
            "unknown filter dimension",
        ),
    ],
)
def test_build_query_rejects_bad_definitions(definition, fragment):
    with pytest.raises(ReportDefinitionError, match=None) as e:
        build_query(definition)
    assert fragment in str(e.value)


# ---- metric view definition --------------------------------------------------------


def test_metric_view_yaml_covers_all_fields():
    y = rb.metric_view_yaml()
    assert y.startswith("version: 0.1")
    assert f"source: {rb._source_fq()}" in y
    for d in rb.DIMENSIONS:
        assert f"- name: {d['name']}" in y
    for m in rb.MEASURES:
        assert f"- name: {m['name']}" in y


def test_metric_view_ddl_shape():
    ddl = rb.metric_view_ddl()
    assert ddl.startswith(f"CREATE OR REPLACE VIEW {rb.view_fq()}")
    assert "WITH METRICS" in ddl and "LANGUAGE YAML" in ddl
    assert ddl.rstrip().endswith("$$")


# ---- business-days closed form -----------------------------------------------------


def _sql_closed_form(s: date, e: date) -> int:
    """Python mirror of the SQL expression in _LEAD_BDAYS (epoch Monday method)."""
    epoch = date(1970, 1, 5)  # a Monday

    def weekdays_through(d: date) -> int:
        n = (d - epoch).days
        return 5 * (n // 7) + min(n % 7 + 1, 5)

    return max(0, weekdays_through(e) - weekdays_through(s))


def test_sql_bdays_matches_python_for_all_weekday_alignments():
    # 8 weeks × 8 weeks of start/end pairs covers every weekday alignment,
    # weekend endpoints, and end <= start.
    start = date(2026, 6, 1)
    for i in range(56):
        for j in range(56):
            a, b = start + timedelta(days=i), start + timedelta(days=j)
            assert _sql_closed_form(a, b) == business_days_between(a, b), (a, b)


# ---- run(): result coercion ---------------------------------------------------------


class _FakeCol:
    def __init__(self, name):
        self.name = name


class _FakeResult:
    def __init__(self, cols, rows):
        class _Schema:
            columns = [_FakeCol(c) for c in cols]

        class _Manifest:
            schema = _Schema()

        class _Data:
            data_array = rows

        self.manifest = _Manifest()
        self.result = _Data()


def test_run_coerces_measures_to_float(monkeypatch):
    b = rb.ReportBuilder()
    b._ready = True
    captured = {}

    def fake_exec(sql, params=None):
        captured["sql"], captured["params"] = sql, params
        return _FakeResult(["type", "items", "avg_lead_bdays"], [["Bug", "7", None]])

    monkeypatch.setattr(b, "_exec", fake_exec)
    out = b._run({"dimensions": ["type"], "measures": ["items", "avg_lead_bdays"]})
    assert out["columns"] == ["type", "items", "avg_lead_bdays"]
    assert out["rows"] == [{"type": "Bug", "items": 7.0, "avg_lead_bdays": None}]
    assert "MEASURE(`items`)" in captured["sql"]


def test_run_unavailable_raises(monkeypatch):
    b = rb.ReportBuilder()
    monkeypatch.setattr(b, "_ensure", lambda: False)
    b._reason = "no warehouse"
    with pytest.raises(RuntimeError, match="no warehouse"):
        b._run({"dimensions": [], "measures": ["items"]})


# ---- saved reports in the app-state store -------------------------------------------


def test_store_save_and_list_reports(monkeypatch):
    s = Store()
    s._ready = True
    calls = []

    def fake_exec(sql, params=None):
        calls.append((sql, params))

        class _R:
            result = type(
                "D", (), {"data_array": [["abc123", "My report", "{}", "2026-07-03"]]}
            )()

        return _R()

    monkeypatch.setattr(s, "_exec", fake_exec)
    s._save_report("u@x.com", "abc123", "My report", '{"measures":["items"]}')
    sql, params = calls[0]
    assert "MERGE INTO" in sql and "saved_reports" in sql
    assert params == {
        "user": "u@x.com",
        "id": "abc123",
        "name": "My report",
        "definition": '{"measures":["items"]}',
    }

    rows = s._list_reports("u@x.com")
    assert rows == [
        {"id": "abc123", "name": "My report", "definition": "{}", "updatedAt": "2026-07-03"}
    ]

    s._delete_report("u@x.com", "abc123")
    del_sql, del_params = calls[-1]
    assert "DELETE FROM" in del_sql and del_params == {"user": "u@x.com", "id": "abc123"}


def test_store_reports_degrade_when_unavailable(monkeypatch):
    s = Store()
    monkeypatch.setattr(s, "_ensure", lambda: False)
    assert s._list_reports("u@x.com") == []  # reads degrade to empty
    with pytest.raises(RuntimeError):  # writes must not silently vanish
        s._save_report("u@x.com", "i", "n", "{}")
    with pytest.raises(RuntimeError):
        s._delete_report("u@x.com", "i")


# ---- routes: audit action names ------------------------------------------------------


def test_builder_audit_action_names():
    from app.main import _action_name

    assert _action_name("POST", "/api/reports/builder/run") == "report.run"
    assert _action_name("PUT", "/api/reports/saved") == "report.save"
    assert _action_name("DELETE", "/api/reports/saved/abc123") == "report.delete"
