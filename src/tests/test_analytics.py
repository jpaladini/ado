"""Tests for the Analytics OData client (mock transport, no live ADO)."""
import httpx
import pytest

from app.ado.analytics import OPEN_CATEGORIES, AnalyticsClient

ROUTES = {
    "/myorg/Demo/_odata/v4.0-preview/WorkItems": {
        "value": [
            {"StateCategory": "InProgress", "Count": 7},
            {"StateCategory": "Proposed", "Count": 5},
            {"StateCategory": "Completed", "Count": 10},
            {"StateCategory": "Resolved", "Count": 2},
        ]
    },
    "/myorg/Demo/_odata/v4.0-preview/WorkItemSnapshot": {
        "value": [
            {"DateValue": "2026-06-27", "Count": 12},
            {"DateValue": "2026-06-28", "Count": 14},
            {"DateValue": "2026-06-29", "Count": 13},
        ]
    },
}


CAPTURED: list[httpx.Request] = []


def _handler(request: httpx.Request) -> httpx.Response:
    CAPTURED.append(request)
    body = ROUTES.get(request.url.path)
    if callable(body):
        body = body(request)
    assert body is not None, f"unexpected {request.url.path}"
    return httpx.Response(200, json=body)


@pytest.fixture
def client() -> AnalyticsClient:
    c = AnalyticsClient(org_url="https://dev.azure.com/myorg", pat="x")
    transport = httpx.MockTransport(_handler)
    c._client = lambda: httpx.AsyncClient(base_url=c.root, transport=transport)  # type: ignore[method-assign]
    return c


def test_derives_analytics_host():
    c = AnalyticsClient(org_url="https://dev.azure.com/myorg", pat="x")
    assert c.root == "https://analytics.dev.azure.com/myorg"


@pytest.mark.asyncio
async def test_count_by_state_category(client: AnalyticsClient):
    cats = await client.count_by_state_category("Demo")
    assert cats == {"InProgress": 7, "Proposed": 5, "Completed": 10, "Resolved": 2}
    open_count = sum(v for k, v in cats.items() if k in OPEN_CATEGORIES)
    assert open_count == 14  # Proposed + InProgress + Resolved, excludes Completed
    assert sum(cats.values()) == 24


@pytest.mark.asyncio
async def test_open_trend(client: AnalyticsClient):
    trend = await client.open_trend("Demo", 7)
    assert [t["count"] for t in trend] == [12, 14, 13]
    assert trend[0]["date"] == "2026-06-27"


# -- business-day math (5-day workweek — the Power BI semantic model, retired) ------


def test_business_days_between():
    from datetime import date

    from app.ado.analytics import business_days_between as bd

    mon, tue, fri = date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 3)
    sat, sun, next_mon = date(2026, 7, 4), date(2026, 7, 5), date(2026, 7, 6)

    assert bd(mon, tue) == 1          # Mon→Tue
    assert bd(mon, fri) == 4          # Mon→Fri same week
    assert bd(fri, next_mon) == 1     # weekend contributes nothing
    assert bd(sat, sun) == 0          # weekend→weekend
    assert bd(sat, next_mon) == 1     # Sat→Mon = the Monday only
    assert bd(mon, next_mon) == 5     # one full week
    assert bd(mon, date(2026, 7, 13)) == 10  # two full weeks
    assert bd(mon, mon) == 0          # same day
    assert bd(tue, mon) == 0          # end before start clamps to 0


# -- 4C report queries --------------------------------------------------------------


def test_filter_builder_escapes_and_combines():
    f = AnalyticsClient._filters(["Issue", "O'Brien Task"], ["Ada Lovelace"], ["X ge 1"])
    assert f == (
        "X ge 1 and (WorkItemType eq 'Issue' or WorkItemType eq 'O''Brien Task') "
        "and (AssignedTo/UserName eq 'Ada Lovelace')"
    )
    assert AnalyticsClient._filters(None, None, ["A"]) == "A"


@pytest.mark.asyncio
async def test_created_per_day_sorted_and_filtered(client: AnalyticsClient):
    ROUTES["/myorg/Demo/_odata/v4.0-preview/WorkItems"] = {
        "value": [
            {"CreatedDateSK": 20260702, "Count": 1},
            {"CreatedDateSK": 20260629, "Count": 2},
        ]
    }
    CAPTURED.clear()
    rows = await client.created_per_day("Demo", 30, types=["Issue"])
    assert rows == [{"dateSK": 20260629, "count": 2}, {"dateSK": 20260702, "count": 1}]
    sent = str(CAPTURED[-1].url)
    assert "CreatedDateSK+ge" in sent or "CreatedDateSK ge" in sent.replace("%20", " ")
    assert "Issue" in sent


@pytest.mark.asyncio
async def test_cycle_time_items_business_days(client: AnalyticsClient):
    # Created Fri 6/26, activated Mon 6/29, closed Wed 7/1:
    # calendar lead = 5 days, but business lead = 3 (Mon,Tue,Wed) and cycle = 2.
    ROUTES["/myorg/Demo/_odata/v4.0-preview/WorkItems"] = {
        "value": [
            {"WorkItemId": 4, "Title": "T", "WorkItemType": "Issue",
             "CycleTimeDays": 2.0, "LeadTimeDays": 5.0,
             "CreatedDate": "2026-06-26T09:00:00Z",
             "ActivatedDate": "2026-06-29T09:00:00Z",
             "ClosedDate": "2026-07-01T09:00:00Z"},
            # never activated → cycle falls back to created
            {"WorkItemId": 5, "Title": "U", "WorkItemType": "Task",
             "CycleTimeDays": 0, "LeadTimeDays": 5.0,
             "CreatedDate": "2026-06-26T09:00:00Z",
             "ActivatedDate": None,
             "ClosedDate": "2026-07-01T09:00:00Z"},
        ]
    }
    items = await client.cycle_time_items("Demo", 30)
    assert items[0]["cycleBdays"] == 2 and items[0]["leadBdays"] == 3
    assert items[0]["cycleDays"] == 2.0  # ADO's calendar values preserved
    assert items[1]["cycleBdays"] == 3  # fallback: created→closed
    assert items[0]["closedDate"] == "2026-07-01"


@pytest.mark.asyncio
async def test_cfd_shapes_rows(client: AnalyticsClient):
    ROUTES["/myorg/Demo/_odata/v4.0-preview/WorkItemSnapshot"] = {
        "value": [
            {"DateValue": "2026-07-01T00:00:00Z", "StateCategory": "InProgress", "Count": 2},
            {"DateValue": "2026-07-01T00:00:00Z", "StateCategory": "Proposed", "Count": 3},
        ]
    }
    rows = await client.cfd("Demo", 7)
    assert rows[0] == {"date": "2026-07-01", "category": "InProgress", "count": 2}


@pytest.mark.asyncio
async def test_open_items_detail_ages(client: AnalyticsClient):
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=9)).isoformat()
    ROUTES["/myorg/Demo/_odata/v4.0-preview/WorkItems"] = {
        "value": [
            {"WorkItemId": 2, "Title": "Stuck", "WorkItemType": "Issue", "State": "To Do",
             "StateCategory": "Proposed", "CreatedDate": f"{old}T01:00:00Z",
             "AssignedTo": {"UserName": "Ada"}},
        ]
    }
    items = await client.open_items_detail("Demo")
    assert items[0]["ageDays"] == 9 and items[0]["assignee"] == "Ada"
