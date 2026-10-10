"""One error shape for every v2 response: {"error": {"code", "message", "details"}}. Never a stack trace."""
from __future__ import annotations

import math

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 409: "job_not_ready",
         413: "payload_too_large", 422: "validation_error", 429: "rate_limited", 500: "internal_error",
         503: "unavailable"}


class ApiError(Exception):
    """Raise from a route to answer with a specific status, code and details."""

    def __init__(self, status: int, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.status, self.message = status, message
        self.code = code or CODES.get(status, "error")
        self.details = details or {}


def error_body(status: int, message: str, code: str | None = None, details: dict | None = None) -> dict:
    return {"error": {"code": code or CODES.get(status, "error"), "message": message, "details": details or {}}}


def error_response(status: int, message: str, code: str | None = None, details: dict | None = None,
                   headers: dict | None = None) -> JSONResponse:
    return JSONResponse(error_body(status, message, code, details), status_code=status, headers=headers)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.message, exc.code, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else CODES.get(exc.status_code, "error")
        return error_response(exc.status_code, message, headers=getattr(exc, "headers", None))

    from ml.live_forecast import LiveForecastError

    @app.exception_handler(LiveForecastError)
    async def _live_forecast_error(request: Request, exc: LiveForecastError):
        return error_response(503, f"the live forecast is unavailable: {exc}")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = [{"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")} for e in exc.errors()]
        return error_response(422, "the request is not valid", details={"fields": fields})
    # Anything else is caught by backend.v2.middleware.GuardMiddleware: logged with the request id, 500 to the client.


def finite(obj):
    """NaN and infinity become null: a step the power flow could not solve has no voltage, and JSON has no NaN."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    return obj


class FiniteJSONResponse(JSONResponse):
    """The v2 response class: JSON with every non-finite number written as null instead of failing the request."""

    def render(self, content) -> bytes:
        return super().render(finite(content))
