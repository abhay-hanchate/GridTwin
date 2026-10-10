"""Addition 1 routes: the precomputed control demonstrations (scripts/control_replay.py) and custom replays as jobs.

GET  /control/runs            every demonstration run's title and summary, plus the near-limit sweep
GET  /control/runs/{run_id}   one run: config, provenance, every state transition, the reactive-rule comparison, timing
POST /control/replay          a demonstration rerun with validated overrides (battery, starting SoC, which actions);
                              a background job like /fixes; refused in offline mode
"""
from __future__ import annotations

import json
from dataclasses import replace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.v2.errors import ApiError
from backend.v2.jobs import cache_key
from backend.v2.routes_decision import _settings, _store
from backend.v2.settings import ROOT, file_version

router = APIRouter()
CONTROL_CODE = sorted((ROOT / "control").glob("*.py"))


def _dir(request: Request):
    return _settings(request).results_dir / "control"


def _read(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.get("/control/runs")
def runs(request: Request) -> dict:
    d = _dir(request)
    return {"runs": _read(d / "index.json"), "near_limit": _read(d / "near_limit.json") or None}


@router.get("/control/runs/{run_id}")
def run_one(request: Request, run_id: str) -> dict:
    d = _dir(request)
    known = sorted(_read(d / "index.json"))
    if run_id not in known:
        raise ApiError(404, f"unknown control run {run_id!r}", details={"runs": known})
    return _read(d / f"{run_id}.json")


class ReplayRequest(BaseModel):
    fixture: str
    soc_start: float | None = Field(None, ge=0.1, le=0.9)
    battery_kw: float | None = Field(None, gt=0, le=60)
    battery_kwh: float | None = Field(None, gt=0, le=240)
    curtail: bool | None = None
    switching: bool | None = None


@router.post("/control/replay")
def replay(request: Request, body: ReplayRequest):
    from control.fixtures import FIXTURES
    s, store = _settings(request), _store(request)
    if body.fixture not in FIXTURES:
        raise ApiError(404, f"unknown control fixture {body.fixture!r}", details={"fixtures": sorted(FIXTURES)})
    if s.offline:
        raise ApiError(503, "offline mode serves only the precomputed control runs; a new replay needs the live engine")
    over = {k: v for k, v in body.model_dump().items() if k != "fixture" and v is not None}
    cfg = replace(FIXTURES[body.fixture], run_id=f"{body.fixture}_custom", **over)
    code = "+".join(file_version(f) for f in CONTROL_CODE)
    key = cache_key("control", s.code_version, code=code, spec=json.dumps(cfg.to_dict(), sort_keys=True))

    def work():
        from control import replay as replay_mod
        return replay_mod.run(cfg).to_dict()
    result, job = store.get_or_submit(key, work)
    return result if result is not None else JSONResponse(job, status_code=202)
