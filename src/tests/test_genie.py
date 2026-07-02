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


def test_extract_query_fetches_chunks_when_no_inline_rows(monkeypatch):
    """Genie can return chunk metadata only (no data_array); rows must be pulled
    from the statement-execution result-chunk endpoint."""
    msg = GenieMessage(
        id="m3",
        space_id="s1",
        conversation_id="c1",
        content="q",
        attachments=[GenieAttachment(query=QueryAttachment(query="SELECT 1"))],
    )

    class FakeCol:
        def __init__(self, name):
            self.name = name

    class FakeChunk:
        def __init__(self, index):
            self.chunk_index = index

    class FakeStmt:
        statement_id = "stmt-1"

        class manifest:
            chunks = [FakeChunk(0), FakeChunk(1)]

            class schema:
                columns = [FakeCol("state"), FakeCol("count")]

        class result:  # chunk metadata only — no data_array
            data_array = None

    class FakeResult:
        statement_response = FakeStmt

    class FakeGenie:
        def get_message_query_result(self, space_id, conv_id, msg_id):
            return FakeResult()

    class FakeChunkResult:
        def __init__(self, rows):
            self.data_array = rows

    class FakeStatementExecution:
        def get_statement_result_chunk_n(self, statement_id, chunk_index):
            assert statement_id == "stmt-1"
            return FakeChunkResult([["To Do", "1"]] if chunk_index == 0 else [["Doing", "2"]])

    class FakeWorkspace:
        genie = FakeGenie()
        statement_execution = FakeStatementExecution()

    monkeypatch.setattr("app.genie._workspace_client", lambda: FakeWorkspace())
    out = _extract(msg, "s1")
    assert out["columns"] == ["state", "count"]
    assert out["rows"] == [["To Do", "1"], ["Doing", "2"]]
