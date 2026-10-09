"""Planning routes: per-phase headroom (cached or a job) and the connection check (computed live, rate-limited)."""
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
    params = {"date": date.isoformat() if date else default_date(_store(request), "risk"), "network": network,
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
    day = body.date.isoformat() if body.date else default_date(_store(request), "risk")
    return compute.connection_payload(day, body.network, body.rule or _settings(request).rule_default, body.node,
                                      body.kw, body.count, body.phase, body.adoption)


@router.get("/hosting")
def hosting(request: Request, date: Date | None = None, network: str = DEFAULT_NETWORK, rule: str | None = None):
    """Probabilistic hosting capacity (share of homes and kW), without a fix and with standard Volt/VAR."""
    params = {"date": date.isoformat() if date else default_date(_store(request), "risk"), "network": network,
              "rule": rule or _settings(request).rule_default}
    return _serve(request, "hosting", params, lambda **p: compute.hosting_payload(p["date"], p["network"], p["rule"]))
