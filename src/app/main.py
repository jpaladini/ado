"""FastAPI app: serves the API (BFF) and the built React SPA from one process."""
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.store import store

app = FastAPI(title="ADO Companion")
app.include_router(api_router)

# (pattern, method, action) — first match names the audit event.
_ACTIONS = [
    (re.compile(r"/workitems/\d+/state$"), "PATCH", "workitem.state"),
    (re.compile(r"/workitems/\d+/comments$"), "POST", "workitem.comment"),
    (re.compile(r"/workitems$"), "POST", "workitem.create"),
    (re.compile(r"/workitems/\d+$"), "PATCH", "workitem.update"),
    (re.compile(r"/pullrequests/\d+/vote$"), "PUT", "pr.approve"),
    (re.compile(r"/pullrequests/\d+/threads$"), "POST", "pr.comment"),
    (re.compile(r"/pullrequests/\d+$"), "PATCH", "pr.status"),
    (re.compile(r"/repos/[^/]+/code-pr$"), "POST", "code.pr"),
    (re.compile(r"^/api/genie/ask$"), "POST", "genie.ask"),
    (re.compile(r"^/api/copilot/chat$"), "POST", "copilot.chat"),
    (re.compile(r"^/api/copilot/sessions$"), "PUT", "copilot.session.save"),
    (re.compile(r"^/api/copilot/sessions/[^/]+$"), "DELETE", "copilot.session.delete"),
    (re.compile(r"^/api/ai/suggest-workitem$"), "POST", "ai.suggest"),
    (re.compile(r"^/api/ai/review-pr$"), "POST", "ai.review"),
    (re.compile(r"^/api/ai/explain-file$"), "POST", "ai.explain"),
    (re.compile(r"^/api/analytics/refresh$"), "POST", "analytics.refresh"),
    (re.compile(r"^/api/reports/builder/run$"), "POST", "report.run"),
    (re.compile(r"^/api/reports/saved$"), "PUT", "report.save"),
    (re.compile(r"^/api/reports/saved/[^/]+$"), "DELETE", "report.delete"),
    (re.compile(r"^/api/settings$"), "PUT", "settings.update"),
]


def _action_name(method: str, path: str) -> str:
    for pattern, m, name in _ACTIONS:
        if m == method and pattern.search(path):
            return name
    return f"{method.lower()} {path}"


class AuditMiddleware:
    """Pure-ASGI audit of mutating API calls: who, what, target, outcome.

    Taps the receive stream for the request body and the send stream for the
    status code — no BaseHTTPMiddleware request-copy quirks, no re-reading.
    """

    MUTATING = ("POST", "PUT", "PATCH", "DELETE")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] not in self.MUTATING
            or not scope["path"].startswith("/api")
        ):
            return await self.app(scope, receive, send)

        chunks: list[bytes] = []
        status_box = {"status": 0}

        async def tapped_receive():
            message = await receive()
            if message["type"] == "http.request":
                chunks.append(message.get("body", b""))
            return message

        async def tapped_send(message):
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, tapped_receive, tapped_send)
        finally:
            try:
                headers = {k.decode(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
                from app.identity import EMAIL_HEADERS

                user = next((headers[h] for h in EMAIL_HEADERS if headers.get(h)), "local")
                store.audit(
                    user=user,
                    action=_action_name(scope["method"], scope["path"]),
                    method=scope["method"],
                    path=scope["path"],
                    status=status_box["status"],
                    detail=b"".join(chunks).decode(errors="replace")[:500],
                )
            except Exception:  # auditing must never break the request
                pass


app.add_middleware(AuditMiddleware)

# The React build (npm run build) lands here. See README.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
INDEX = STATIC_DIR / "index.html"

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    """Serve the SPA, falling back to index.html for client-side routes."""
    candidate = STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    if INDEX.exists():
        return FileResponse(INDEX)
    return JSONResponse(
        {"detail": "Frontend not built yet. Run `npm run build` in ./frontend."},
        status_code=200,
    )
