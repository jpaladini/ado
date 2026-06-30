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


def _handler(request: httpx.Request) -> httpx.Response:
    body = ROUTES.get(request.url.path)
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
