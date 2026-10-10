"""GET /catalog and POST /whatif: run any combination of registered changes and fixes on the design day."""
from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

import numpy as np

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from backend.v2 import compute
from backend.v2.errors import ApiError
from backend.v2.jobs import cache_key
from backend.v2.routes_decision import DEFAULT_NETWORK, _settings, _store, default_date
from backend.v2.settings import ROOT, file_version
from engine.fixes.battery import solve_with_battery
from engine.registry import REGISTRY, catalog
from engine.solver import DaySolver
from engine.types import Controls
from engine.violations import evaluate, summarise

router = APIRouter()
MAX_ITEMS = 6
WHATIF_CODE = (ROOT / "engine" / "registry.py", Path(__file__))     # their hashes join the cache key


def whatif_payload(date: str, network: str, rule: str, changes: list[dict], fixes: list[dict],
                   adoption: float = 1.0) -> dict:
    """Three runs of the same day: `today` (the street as it is), `before` (with the changes, no fix) and `after`
    (with the changes and the fixes). A what-if compares `after` with `today`; `before` shows the changes alone."""
    from engine.fixes.catalog import worst_node
    from engine.registry import REGISTRY, Battery, battery_spec
    r = compute.rule(rule)
    net = compute.network(network)
    if adoption < 1.0:
        net, design = compute.planning_street(date, network, adoption)
    else:
        design = compute._design(compute.robust_set(compute.scenarios(date, net)))
    today_net, today_design = net, design
    applied = []
    for item in changes:
        entry = REGISTRY[item["id"]]
        net, design = entry.fn(net, design, entry.params(**item.get("params", {})))
        applied.append(item["id"])
    controls, battery = Controls(), None
    for item in fixes:
        entry = REGISTRY[item["id"]]
        params = entry.params(**item.get("params", {}))
        controls = entry.fn(controls, params)
        if isinstance(params, Battery):
            battery = battery_spec(params, worst_node(net, design))
    before = DaySolver(net, asymmetric=True).solve(design)
    today = DaySolver(today_net, asymmetric=True).solve(today_design) if applied else before
    after = solve_with_battery(net, design, battery, r, controls) if battery else \
        DaySolver(net, asymmetric=True).solve(design, controls)
    out = {"date": date, "network": network, "rule": r.id, "changes": applied, "fixes": [f["id"] for f in fixes],
           "t": compute._labels(design.t), "limits_v": {"min": r.vmin_v, "max": r.vmax_v},
           "nodes": [int(n) for n in net.lv_nodes], "provenance": compute.PROVENANCE}
    for key, res in (("today", today), ("before", before), ("after", after)):
        v = evaluate(res, r)
        out[key] = {"summary": summarise(res, v), "unsafe": [bool(x) for x in v.unsafe[0]],
                    "max_v": compute._peak_v(res),
                    "node_max_v": [[round(float(x) * compute.NOMINAL_V, 1) for x in row] for row in np.nanmax(res.u_pu[0], axis=2)]}
    return out


class Item(BaseModel):
    id: str
    params: dict = Field(default_factory=dict)


class WhatIf(BaseModel):
    date: Date | None = None
    network: str = DEFAULT_NETWORK
    rule: str | None = None
    adoption: float = Field(1.0, ge=0, le=1, description="share of homes with solar")
    changes: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS)
    fixes: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS)


@router.get("/catalog")
def get_catalog() -> list[dict]:
    """Every registered change, fix and check, with the JSON schema of its parameters."""
    return catalog()


def _validated(items: list[Item], kind: str) -> list[dict]:
    out = []
    for item in items:
        entry = REGISTRY.get(item.id)
        if entry is None or entry.kind != kind:
            valid = sorted(e.id for e in REGISTRY.values() if e.kind == kind)
            raise ApiError(404, f"unknown {kind} {item.id!r}", details={"valid": valid})
        try:
            params = entry.params(**item.params).model_dump()
        except ValidationError as exc:
            raise ApiError(422, f"invalid parameters for {item.id}",
                           details={"fields": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}) from exc
        out.append({"id": item.id, "params": params})
    return out


def normalise(spec: WhatIf, s, store) -> tuple[dict, str]:
    """The normalised spec (defaults filled) and its cache key; the nightly precompute uses the same function."""
    compute.check_network(spec.network)
    norm = {"date": spec.date.isoformat() if spec.date else default_date(store, "whatif"), "network": spec.network,
            "rule": compute.rule(spec.rule or s.rule_default).id, "adoption": spec.adoption,
            "changes": _validated(spec.changes, "change"), "fixes": _validated(spec.fixes, "fix")}
    key = cache_key("whatif", s.code_version, code="+".join(file_version(f) for f in WHATIF_CODE),
                    spec=json.dumps(norm, sort_keys=True))
    return norm, key


@router.post("/whatif")
def whatif(request: Request, spec: WhatIf):
    """Same spec twice = one computation (the cache key is the normalised spec)."""
    s, store = _settings(request), _store(request)
    norm, key = normalise(spec, s, store)
    if s.offline:
        result = store.cached(key)
        if result is None:
            raise ApiError(503, "offline mode serves only precomputed results; what-if needs the live engine")
        return result
    result, job = store.get_or_submit(key, lambda: whatif_payload(**norm))
    return result if result is not None else JSONResponse(job, status_code=202)
