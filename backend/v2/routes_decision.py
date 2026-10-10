"""Decision routes: /risk, /fixes, /simulate and /jobs/{id}.

A cached result answers at once. A miss starts (or joins) a background job and answers 202 with
{"status": "running", "job_id"}; the dashboard polls /jobs/{id}. In offline mode a miss is 503: only the bundled
nightly results are served. Omitting `date` means the latest date the nightly run precomputed.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.v2 import compute
from backend.v2.errors import ApiError
from backend.v2.jobs import JobStore, cache_key
from backend.v2.settings import Settings

router = APIRouter()
DEMO_DATE = "2025-05-15"
DEFAULT_NETWORK = "benchmark_250"


def _store(request: Request) -> JobStore:
    return request.app.state.jobs


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def default_date(store: JobStore, route: str) -> str:
    dates = [e["date"] for e in store.index().get("entries", []) if e.get("route") == route]
    return max(dates) if dates else DEMO_DATE


def check_date(request: Request, day: str) -> None:
    """404 at once for a day with no forecast: outside the solar archive and outside today to the live horizon."""
    from backend.v2.live_inputs import today_ist
    today = today_ist()
    live = {"first": today.isoformat(), "last": (today + timedelta(days=_settings(request).live_horizon_days)).isoformat()}
    try:
        fc = compute._solar_table()
        archive = {"first": fc.index.min().date().isoformat(), "last": fc.index.max().date().isoformat()}
    except (OSError, ValueError):            # no archive file here: the range is unknown, so the job decides
        return
    if live["first"] <= day <= live["last"] or archive["first"] <= day <= archive["last"]:
        return
    raise ApiError(404, f"no forecast for {day}: choose a day in the {archive['first']} to {archive['last']} archive "
                        f"or today to {live['last']} (live)",
                   details={"date": day, "archive": archive, "live": live})


def _serve(request: Request, route: str, params: dict, fn) -> object:
    s, store = _settings(request), _store(request)
    check_date(request, params["date"])
    if "network" in params:                                  # a portfolio route has none
        compute.check_network(params["network"])             # validate before any work: 404 on unknown ids
    params["rule"] = compute.rule(params["rule"]).id
    from backend.v2.live_inputs import is_live, today_ist
    if is_live(params["date"]):
        params["issued"] = today_ist().isoformat()          # tomorrow's forecast changes as tomorrow approaches
    key = cache_key(route, s.code_version, **params)
    if s.offline:
        result = store.cached(key)
        if result is None:
            raise ApiError(503, "offline mode serves only precomputed results; this request was not precomputed",
                           details={"route": route, **params})
        return result
    result, job = store.get_or_submit(key, lambda: fn(**params))
    return result if result is not None else JSONResponse(job, status_code=202)


@router.get("/risk")
def risk(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
         fix: str = "none"):
    """Tomorrow's P(unsafe) per 15 minutes, expected unsafe hours, watch/act level and per-limit shares."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "risk"), "network": network,
              "rule": rule or _settings(request).rule_default, "fix": fix}
    compute._controls(fix)
    return _serve(request, "risk", params, lambda **p: compute.risk_payload(p["date"], p["network"], p["rule"], p["fix"]))


@router.get("/fixes")
def fixes(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None):
    """The fix tournament: ranked safe fixes, or the honest no-safe-action verdict with the binding limit."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "fixes"), "network": network,
              "rule": rule or _settings(request).rule_default}
    return _serve(request, "fixes", params, lambda **p: compute.fixes_payload(p["date"], p["network"], p["rule"]))


@router.get("/street")
def street(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
           fix: str = "none"):
    """The street as a schematic and the design day quarter hour by quarter hour: each home's voltage on its phase,
    per-phase power and neutral current on every wire, without and (with `fix`) with a fix from the tournament."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "risk"), "network": network,
              "rule": rule or _settings(request).rule_default, "fix": fix}
    return _serve(request, "street", params,
                  lambda **p: compute.street_payload(p["date"], p["network"], p["rule"], p["fix"]))


@router.get("/calendar")
def calendar(request: Request):
    """The days that can be asked for: tomorrow (live forecast) and every day of the solar forecast archive, plus
    the days already computed (instant, and the only ones served offline)."""
    from backend.v2.live_inputs import today_ist
    fc = compute._solar_table()
    tomorrow = (today_ist() + timedelta(days=1)).isoformat()
    ready = sorted({e["date"] for e in _store(request).index().get("entries", []) if e.get("route") == "risk"})
    return {"tomorrow": tomorrow, "archive": {"first": fc.index.min().date().isoformat(), "last": fc.index.max().date().isoformat()},
            "ready": ready, "offline": _settings(request).offline}


@router.get("/simulate")
def simulate(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
             fix: str = "none"):
    """The design-case day without and with one fix, step by step."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "simulate"), "network": network,
              "rule": rule or _settings(request).rule_default, "fix": fix}
    compute._controls(fix)
    return _serve(request, "simulate", params,
                  lambda **p: compute.simulate_payload(p["date"], p["network"], p["rule"], p["fix"]))


@router.get("/jobs/{job_id}")
def job(request: Request, job_id: str):
    view = _store(request).view(job_id)
    if view is None:
        raise ApiError(404, f"unknown job {job_id!r}")
    return view
