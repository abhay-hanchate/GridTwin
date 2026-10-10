"""Read-only v2 routes: voltage rules, liveness, readiness and Prometheus metrics."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from backend.v2 import metrics
from backend.v2.errors import ApiError
from backend.v2.schemas import Health, Readiness, Rule
from backend.v2.settings import Settings
from engine.archetypes import ARCHETYPES, CONDUCTORS, list_archetypes
from engine.rules import load_rules

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/rules", response_model=list[Rule])
def rules() -> list[dict]:
    """Every voltage rule the engine can check, with its source and how well it is verified."""
    return [r.as_dict() for r in load_rules().values()]


@router.get("/networks")
def networks() -> list[dict]:
    """The feeder archetypes and what is real about each (conductor data) and what is not (topology, reactance)."""
    out = []
    for row in list_archetypes():
        a, cond = ARCHETYPES[row["id"]], CONDUCTORS[row["conductor"]]
        out.append({**row, "description": a.note, "conductor_r_ohm_per_km": cond["r_ohm_per_km"],
                    "conductor_ampacity_a": cond["i_a"],
                    "provenance": {"topology": "benchmark: SimBench 1-LV-rural2 scaled in length, not a surveyed Indian feeder",
                                   "conductor": "IS 398 Part II (1996) ACSR table",
                                   "reactance": "benchmark assumption" if row["id"] == "benchmark_250" else "estimate, not from the standard"}})
    return out


@router.get("/health", response_model=Health)
def health(request: Request) -> dict:
    """Liveness: the process answers. Says nothing about data or models (that is /readiness)."""
    s = _settings(request)
    return {"status": "ok", "version": s.code_version, "env": s.env}


def readiness_checks(s: Settings) -> dict[str, bool]:
    if s.offline:
        index = s.results_dir / "v2" / "index.json"
        try:
            saved = json.loads(index.read_text(encoding="utf-8")).get("code_version")
        except (OSError, ValueError):
            return {"precomputed_results": False, "precomputed_match_code": False}
        # Results keyed to an older code version would never be found: offline would serve nothing.
        return {"precomputed_results": True, "precomputed_match_code": saved == s.code_version}
    try:
        rules_ok = bool(load_rules())
    except (OSError, ValueError):
        rules_ok = False
    return {
        "voltage_rules": rules_ok,
        "legacy_profiles": all((s.data_dir / f"{name}.parquet").is_file()
                               for name in ("load_kw", "pv_kw_per_kwp", "upstream_vm_pu")),
        "district_profiles": all((s.data_dir / "v2" / f"{name}_mathura.parquet").is_file()
                                 for name in ("load_kw", "pv_kw_per_kwp", "upstream_vm_pu")),
        "solar_model": (s.model_dir / "solar_v2_manifest.json").is_file(),
    }


@router.get("/readiness", response_model=Readiness)
def readiness(request: Request) -> dict:
    """Ready only when the data and models the routes need are present; 503 with the failing checks otherwise."""
    s = _settings(request)
    checks = readiness_checks(s)
    mode = "offline" if s.offline else "online"
    if not all(checks.values()):
        missing = sorted(k for k, ok in checks.items() if not ok)
        raise ApiError(503, f"not ready: missing {', '.join(missing)}", details={"mode": mode, "checks": checks})
    return {"ready": True, "mode": mode, "checks": checks}


@router.get("/results")
def results(request: Request) -> dict:
    """Every gate and headline (data/results/results.json, written by python -m scripts.evaluate). Failed gates
    are included as failed; the Proof page shows them."""
    path = _settings(request).results_dir / "results.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApiError(503, "results.json is missing; run python -m scripts.evaluate") from exc


@router.get("/metrics", include_in_schema=False)
def prometheus() -> Response:
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)
