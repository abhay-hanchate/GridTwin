"""Plain ASGI middleware for API v2: request id, JSON access log, security headers, body-size limit, per-client rate
limit, metrics, and a last-resort 500 that never leaks a stack trace.

Plain ASGI (rather than Starlette's BaseHTTPMiddleware) so streamed request bodies can be counted and cut off.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from backend.v2 import metrics
from backend.v2.errors import error_body
from backend.v2.settings import Settings

access_log = logging.getLogger("gridtwin.access")
log = logging.getLogger("gridtwin.v2")

SECURITY_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"same-origin"),
                    (b"x-frame-options", b"DENY"), (b"cache-control", b"no-store")]


class _BodyTooLarge(Exception):
    pass


class RateLimiter:
    """Sliding one-minute window per client and path; thread-safe, in process (enough for one container)."""

    def __init__(self, per_minute: int, window_s: float = 60.0):
        self.per_minute, self.window_s = per_minute, window_s
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str, path: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[(client, path)]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


class GuardMiddleware:
    def __init__(self, app, settings: Settings):
        self.app, self.settings = app, settings
        self.limiter = RateLimiter(settings.rate_limit_per_minute)

    @staticmethod
    def _relative_path(scope) -> str:
        path, root = scope.get("path", ""), scope.get("root_path", "")
        return path[len(root):] if root and path.startswith(root) else path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex[:16]
        started, state = time.perf_counter(), {"status": 500, "started": False}
        rel = self._relative_path(scope)

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                state["status"], state["started"] = message["status"], True
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", request_id.encode()), *SECURITY_HEADERS]
            await send(message)

        async def respond(status: int, message: str, extra_headers: list | None = None):
            body = json.dumps(error_body(status, message, details={"request_id": request_id})).encode()
            await send_wrapped({"type": "http.response.start", "status": status,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(body)).encode()), *(extra_headers or [])]})
            await send_wrapped({"type": "http.response.body", "body": body})

        limit = self.settings.max_body_bytes
        received = 0

        async def receive_limited():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        try:
            length = dict(scope.get("headers", [])).get(b"content-length")
            if length is not None and length.isdigit() and int(length) > limit:
                await respond(413, f"request body is larger than {limit} bytes")
            elif rel in self.settings.rate_limited_paths and not self.limiter.allow(
                    (scope.get("client") or ("unknown",))[0], rel):
                await respond(429, f"more than {self.settings.rate_limit_per_minute} requests a minute",
                              [(b"retry-after", b"60")])
            else:
                await self.app(scope, receive_limited, send_wrapped)
        except _BodyTooLarge:
            if not state["started"]:
                await respond(413, f"request body is larger than {limit} bytes")
        except Exception:
            log.exception("unhandled error, request id %s, path %s", request_id, rel)
            if not state["started"]:
                await respond(500, "internal error; quote the request id when reporting it")
        finally:
            duration = time.perf_counter() - started
            route = scope.get("route")
            label = getattr(route, "path", None) or "unmatched"
            metrics.REQUESTS.labels(label, str(state["status"])).inc()
            metrics.LATENCY.labels(label).observe(duration)
            access_log.info(json.dumps({"request_id": request_id, "method": scope.get("method"), "route": label,
                                        "status": state["status"], "duration_ms": round(duration * 1000, 1),
                                        "version": self.settings.code_version}))
