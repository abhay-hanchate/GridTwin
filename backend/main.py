"""GridTwin: API v2 under /api/v2 and the built dashboard, from one process.

Run:  uvicorn backend.main:app --reload

The Round 1 routes (/api/run, /api/actions, ...) were removed in P10.12; the release tag v2.0.0 still contains
them.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.v2.app import create_app as create_v2_app
from backend.v2.errors import CODES, error_response

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="GridTwin", version="2", docs_url=None, redoc_url=None)
    # API v2 is its own sub-application: own error model, middleware, CORS and docs at /api/v2/docs.
    app.mount("/api/v2", create_v2_app())

    # Every /api path answers with the v2 error shape, including the removed Round 1 routes.
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else CODES.get(exc.status_code, "error")
        return error_response(exc.status_code, message, headers=getattr(exc, "headers", None))

    # Serve the built dashboard from the same process when it exists.
    dist = FRONTEND_DIST
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):         # an unknown API path is an API 404, not the page
                return error_response(404, f"no API route /{path}; the API is under /api/v2")
            file = dist / path
            if path and file.is_file() and dist.resolve() in file.resolve().parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
