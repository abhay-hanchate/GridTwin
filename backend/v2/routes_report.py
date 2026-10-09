"""GET /report: the printable evening report, built from the cached /risk and /fixes results."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backend.v2 import compute
from backend.v2.errors import ApiError
from backend.v2.jobs import cache_key
from backend.v2.routes_decision import DEFAULT_NETWORK, _settings, _store, default_date
from engine.report import render_report

router = APIRouter()


@router.get("/report")
def report(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
           lang: Literal["en", "hi"] = "en"):
    s, store = _settings(request), _store(request)
    compute.check_network(network)
    day = date.isoformat() if date else default_date(store, "risk")
    rule_id = compute.rule(rule or s.rule_default).id
    parts = {
        "risk": (cache_key("risk", s.code_version, date=day, network=network, rule=rule_id, fix="none"),
                 lambda: compute.risk_payload(day, network, rule_id, "none")),
        "fixes": (cache_key("fixes", s.code_version, date=day, network=network, rule=rule_id),
                  lambda: compute.fixes_payload(day, network, rule_id)),
    }
    results = {}
    for name, (key, fn) in parts.items():
        if s.offline:
            results[name] = store.cached(key)
            if results[name] is None:
                raise ApiError(503, f"offline mode: the {name} result for this report was not precomputed")
            continue
        result, job = store.get_or_submit(key, fn)
        if result is None:
            return JSONResponse(job, status_code=202)          # the report is ready when both parts are
        results[name] = result
    return HTMLResponse(render_report(results["risk"], results["fixes"], lang, network_label=network))
