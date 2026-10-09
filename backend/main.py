"""GridTwin: API v2 under /api/v2 and the built dashboard, from one process.

Run:  uvicorn backend.main:app --reload

The Round 1 routes (/api/run, /api/actions, ...) were removed in P10.12; the release tag v2.0.0 still contains
them.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.v2.app import create_app as create_v2_app

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="GridTwin", version="2", docs_url=None, redoc_url=None)
    # API v2 is its own sub-application: own error model, middleware, CORS and docs at /api/v2/docs.
    app.mount("/api/v2", create_v2_app())

    # Serve the built dashboard from the same process when it exists.
    dist = FRONTEND_DIST
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):         # an unknown API path is an API 404, not the page
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            file = dist / path
            if path and file.is_file() and dist.resolve() in file.resolve().parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
