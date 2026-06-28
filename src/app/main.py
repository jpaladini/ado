"""FastAPI app: serves the API (BFF) and the built React SPA from one process."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

app = FastAPI(title="ADO Companion")
app.include_router(api_router)

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
