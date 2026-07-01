"""Tests for Genie response flattening (real SDK dataclasses, no workspace)."""
from databricks.sdk.service.dashboards import (
    GenieAttachment,
    GenieMessage,
    QueryAttachment,
    TextAttachment,
)

from app.genie import _extract


def test_extract_text_only():
    msg = GenieMessage(
        id="m1",
        space_id="s1",
        conversation_id="c1",
        content="q",
        attachments=[GenieAttachment(text=TextAttachment(content="There are 14 open items."))],
    )
    out = _extract(msg, "s1")
    assert out["conversationId"] == "c1"
    assert out["text"] == ["There are 14 open items."]
    assert out["columns"] == [] and out["rows"] == []
    assert out["sql"] is None


def test_extract_query_pulls_result(monkeypatch):
    msg = GenieMessage(
        id="m2",
        space_id="s1",
        conversation_id="c1",
        content="q",
        attachments=[
            GenieAttachment(
                query=QueryAttachment(query="SELECT state, count(*) FROM t GROUP BY state",
                                      description="Open items by state")
            )
        ],
    )

    class FakeCol:
        def __init__(self, name):
            self.name = name

    class FakeStmt:
        class manifest:
            class schema:
                columns = [FakeCol("state"), FakeCol("count")]

        class result:
            data_array = [["Active", "7"], ["New", "5"]]

    class FakeResult:
        statement_response = FakeStmt

    class FakeGenie:
        def get_message_query_result(self, space_id, conv_id, msg_id):
            assert (space_id, conv_id, msg_id) == ("s1", "c1", "m2")
            return FakeResult()

    class FakeWorkspace:
        genie = FakeGenie()

    monkeypatch.setattr("app.genie._workspace_client", lambda: FakeWorkspace())
    out = _extract(msg, "s1")
    assert out["sql"].startswith("SELECT")
    assert out["queryDescription"] == "Open items by state"
    assert out["columns"] == ["state", "count"]
    assert out["rows"] == [["Active", "7"], ["New", "5"]]
