"""API v2 application. Mounted by backend/main.py at /api/v2 as its own sub-application, so the v2 error model,
middleware and docs (/api/v2/docs) never change the legacy /api routes."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.v2 import errors, routes_core, routes_decision, routes_planning
from backend.v2.jobs import JobStore
from backend.v2.middleware import GuardMiddleware
from backend.v2.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="GridTwin API v2", version=settings.code_version,
                  description="Decision support for low-voltage streets with rooftop solar. "
                              "Every number carries its provenance: observed, modeled or benchmark.")
    app.state.settings = settings
    app.state.jobs = JobStore(settings.results_dir)
    errors.install(app)
    app.include_router(routes_core.router)
    app.include_router(routes_decision.router)
    app.include_router(routes_planning.router)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST"],
                       allow_headers=["content-type"])
    app.add_middleware(GuardMiddleware, settings=settings)      # added last = outermost: sees every request
    return app
