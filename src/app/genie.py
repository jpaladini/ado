"""Databricks Genie (NL analytics) client.

Runs inside the Databricks App, where WorkspaceClient() auto-authenticates as the
app's service principal. The Genie Space ID is per-workspace config: it comes from
the GENIE_SPACE_ID env var if set, otherwise from the `ado/genie_space_id` secret
at runtime (the app already holds READ on the `ado` scope — secret ACLs are
scope-level). If neither exists, Genie is simply "not configured" and the API
degrades gracefully; the rest of the app is unaffected.
"""
import base64
import logging
from functools import lru_cache
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

SECRET_SCOPE = "ado"
SECRET_KEY = "genie_space_id"


class GenieNotConfigured(RuntimeError):
    """Raised when no Genie Space ID is available."""


@lru_cache(maxsize=1)
def _workspace_client():
    # Imported lazily so the app still boots in environments without Databricks auth.
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


@lru_cache(maxsize=1)
def resolve_space_id() -> str:
    if settings.genie_space_id:
        return settings.genie_space_id
    try:
        w = _workspace_client()
        secret = w.secrets.get_secret(SECRET_SCOPE, SECRET_KEY)
        value = base64.b64decode(secret.value or "").decode().strip()
        if value:
            return value
    except Exception as e:  # missing scope/key, no auth, etc. — all mean "not configured"
        log.info("Genie space id lookup failed: %s", e)
    raise GenieNotConfigured(
        "No Genie Space configured. Set the ado/genie_space_id secret (see docs/GENIE.md)."
    )


def genie_available() -> bool:
    try:
        resolve_space_id()
        return True
    except GenieNotConfigured:
        return False


def _extract(message: Any, space_id: str) -> dict[str, Any]:
    """Flatten a GenieMessage into text + optional tabular result."""
    out: dict[str, Any] = {
        "conversationId": message.conversation_id,
        "messageId": message.id,
        "status": message.status.value if getattr(message, "status", None) else None,
        "text": [],
        "sql": None,
        "queryDescription": None,
        "columns": [],
        "rows": [],
    }
    has_query = False
    for att in message.attachments or []:
        if att.text and att.text.content:
            out["text"].append(att.text.content)
        if att.query:
            has_query = True
            out["sql"] = att.query.query
            out["queryDescription"] = att.query.description

    if has_query:
        w = _workspace_client()
        result = w.genie.get_message_query_result(space_id, message.conversation_id, message.id)
        stmt = result.statement_response
        if stmt and stmt.manifest and stmt.manifest.schema and stmt.manifest.schema.columns:
            out["columns"] = [c.name for c in stmt.manifest.schema.columns]
        if stmt and stmt.result and stmt.result.data_array:
            out["rows"] = stmt.result.data_array

    if getattr(message, "error", None):
        out["error"] = getattr(message.error, "error", None) or str(message.error)
    return out


async def ask(question: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Ask Genie a question (optionally continuing a conversation). Blocking SDK
    calls are pushed to a thread so the event loop stays free."""
    import anyio

    space_id = resolve_space_id()

    def _call() -> dict[str, Any]:
        w = _workspace_client()
        if conversation_id:
            msg = w.genie.create_message_and_wait(space_id, conversation_id, question)
        else:
            msg = w.genie.start_conversation_and_wait(space_id, question)
        return _extract(msg, space_id)

    return await anyio.to_thread.run_sync(_call)
