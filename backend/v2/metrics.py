"""Prometheus metrics for API v2 on a dedicated registry (so tests that rebuild the app never double-register)."""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry()
REQUESTS = Counter("gridtwin_requests_total", "API v2 requests", ["route", "status"], registry=REGISTRY)
LATENCY = Histogram("gridtwin_request_seconds", "API v2 request duration", ["route"], registry=REGISTRY,
                    buckets=(0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 120))
CACHE = Counter("gridtwin_cache_total", "Cache lookups", ["result"], registry=REGISTRY)          # hit or miss
SOLVER_CONVERGENCE = Gauge("gridtwin_solver_convergence_ratio", "Share of converged steps in the last run",
                           registry=REGISTRY)
JOBS_QUEUED = Gauge("gridtwin_jobs_queued", "Background jobs waiting or running", registry=REGISTRY)
LAST_NIGHTLY = Gauge("gridtwin_last_nightly_timestamp_seconds", "Unix time of the last successful nightly run",
                     registry=REGISTRY)


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
