import json
import logging

import pytest
from fastapi import APIRouter, Query
from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.errors import ApiError
from backend.v2.middleware import RateLimiter
from backend.v2.settings import Settings


def _client(**overrides) -> TestClient:
    app = create_app(Settings(code_version="test", **overrides))
    extra = APIRouter()

    @extra.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    @extra.get("/typed")
    def typed(kw: float = Query(..., gt=0, le=50)):
        return {"kw": kw}

    @extra.get("/conflict")
    def conflict():
        raise ApiError(409, "job not ready", details={"job_id": "abc"})

    @extra.post("/whatif")
    def whatif(body: dict):
        return {"ok": True}

    app.include_router(extra)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    return _client(rate_limit_per_minute=3, max_body_bytes=2000)


def test_unknown_route_uses_the_error_model(client):
    r = client.get("/no-such-thing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found" and set(r.json()["error"]) == {"code", "message", "details"}


def test_validation_errors_name_the_field(client):
    r = client.get("/typed", params={"kw": 500})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["details"]["fields"][0]["loc"][-1] == "kw"


def test_api_error_carries_status_code_and_details(client):
    r = client.get("/conflict")
    assert r.status_code == 409 and r.json()["error"] == {"code": "job_not_ready", "message": "job not ready",
                                                          "details": {"job_id": "abc"}}


def test_an_unexpected_exception_is_a_500_without_a_stack_trace(client, caplog):
    with caplog.at_level(logging.ERROR, logger="gridtwin.v2"):
        r = client.get("/boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
    assert r.json()["error"]["details"]["request_id"] == r.headers["x-request-id"]
    assert "secret internal detail" in caplog.text                 # the detail goes to the log only


def test_every_response_has_a_request_id_and_security_headers(client):
    r = client.get("/health")
    assert len(r.headers["x-request-id"]) == 16
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "same-origin"


def test_an_oversize_body_is_refused_before_the_route_runs(client):
    r = client.post("/whatif", content=json.dumps({"x": "a" * 5000}), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_rate_limit_applies_only_to_the_expensive_routes(tmp_path):
    # The real /whatif route is mounted first, so it answers (200 cached or 202 job); a temporary results directory
    # keeps its job and cache out of data/results/v2. Only the limiter's decision is under test here.
    c = _client(rate_limit_per_minute=3, results_dir=tmp_path)
    codes = [c.post("/whatif", json={}).status_code for _ in range(4)]
    assert 429 not in codes[:3] and codes[3] == 429
    r = c.post("/whatif", json={})
    assert r.json()["error"]["code"] == "rate_limited" and r.headers["retry-after"] == "60"
    assert all(c.get("/health").status_code == 200 for _ in range(10))


def test_rate_limiter_window_slides():
    lim = RateLimiter(per_minute=2)
    assert lim.allow("a", "/x", now=0) and lim.allow("a", "/x", now=1) and not lim.allow("a", "/x", now=2)
    assert lim.allow("b", "/x", now=2)                              # per client
    assert lim.allow("a", "/x", now=61)                             # the first hit left the window


def test_cors_allows_only_configured_origins():
    c = _client(cors_origins="https://ok.example")
    ok = c.get("/health", headers={"origin": "https://ok.example"})
    bad = c.get("/health", headers={"origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "https://ok.example"
    assert "access-control-allow-origin" not in bad.headers


def test_v2_is_mounted_without_changing_the_legacy_error_shape():
    from backend.main import app
    c = TestClient(app)
    assert c.get("/api/v2/health").json()["status"] == "ok"
    assert "error" in c.get("/api/v2/nope").json()
    assert "detail" in c.get("/api/run", params={"scenario": "S9"}).json()        # legacy keeps {"detail": ...}
