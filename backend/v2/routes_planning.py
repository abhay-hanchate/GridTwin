"""Planning routes: per-phase headroom, hosting capacity, where to meter first, the R/X map and the transformer ranking
(cached or a job), and the connection check (computed live, rate-limited)."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from backend.v2 import compute
from backend.v2.routes_decision import DEFAULT_NETWORK, _serve, _settings, _store, default_date

router = APIRouter()


@router.get("/headroom")
def headroom(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
             adoption: float = Query(compute.DEFAULT_ADOPTION, ge=0, le=1)):
    """Extra kW of rooftop solar per phase near the transformer and at the far end, beside the flat state caps."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "headroom"), "network": network,
              "rule": rule or _settings(request).rule_default, "adoption": adoption}
    return _serve(request, "headroom", params,
                  lambda **p: compute.headroom_payload(p["date"], p["network"], p["rule"], p["adoption"]))


class ConnectionRequest(BaseModel):
    node: int = Field(..., ge=0)
    kw: float = Field(..., gt=0, le=50)
    count: int = Field(1, ge=1, le=50)
    phase: Literal["A", "B", "C"] | None = None
    network: str = DEFAULT_NETWORK
    rule: str | None = None
    date: Date | None = None
    adoption: float = Field(compute.DEFAULT_ADOPTION, ge=0, le=1)


@router.post("/connection-check")
def connection_check(request: Request, body: ConnectionRequest):
    """Approve, approve with conditions, or refuse; with the phase to use and the binding limit."""
    compute.check_network(body.network)
    day = body.date.isoformat() if body.date else default_date(_store(request), "headroom")    # planning's own date
    return compute.connection_payload(day, body.network, body.rule or _settings(request).rule_default, body.node,
                                      body.kw, body.count, body.phase, body.adoption)


@router.get("/hosting")
def hosting(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None):
    """Probabilistic hosting capacity (share of homes and kW), without a fix and with standard Volt/VAR."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "hosting"), "network": network,
              "rule": rule or _settings(request).rule_default}
    return _serve(request, "hosting", params, lambda **p: compute.hosting_payload(p["date"], p["network"], p["rule"]))


def _planning_params(request: Request, route: str, date: Date | None, network: str | None, rule: str | None,
                     adoption: float) -> dict:
    params = {"date": date.isoformat() if date else default_date(_store(request), route),
              "rule": rule or _settings(request).rule_default, "adoption": adoption}
    return params if network is None else {**params, "network": network}


@router.get("/meter-sites")
def meter_sites(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
                adoption: float = Query(compute.DEFAULT_ADOPTION, ge=0, le=1)):
    """Where one smart meter reveals the most: voltage rise per kW at the peak step times the homes downstream."""
    params = _planning_params(request, "meter-sites", date, network, rule, adoption)
    return _serve(request, "meter-sites", params,
                  lambda **p: compute.meter_sites_payload(p["date"], p["network"], p["rule"], p["adoption"]))


@router.get("/rx-map")
def rx_map(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None,
           adoption: float = Query(compute.DEFAULT_ADOPTION, ge=0, le=1)):
    """Peak voltage with and without standard Volt/VAR as line R and X are scaled: where Volt/VAR helps."""
    params = _planning_params(request, "rx-map", date, network, rule, adoption)
    return _serve(request, "rx-map", params,
                  lambda **p: compute.rx_map_payload(p["date"], p["network"], p["rule"], p["adoption"]))


@router.get("/transformers")
def transformers(request: Request, date: Date | None = None, rule: str | None = None,
                 adoption: float = Query(compute.DEFAULT_ADOPTION, ge=0, le=1)):
    """The street archetypes as a portfolio, ordered by how much of their safe room is already used."""
    params = _planning_params(request, "transformers", date, None, rule, adoption)
    return _serve(request, "transformers", params,
                  lambda **p: compute.transformers_payload(p["date"], p["rule"], p["adoption"]))
