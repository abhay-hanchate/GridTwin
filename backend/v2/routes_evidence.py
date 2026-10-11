"""Evidence routes: every file the ENR-02 brief asks to be submitted, listed and downloadable, read-only.

GET /evidence/files         the evidence files grouped by what the brief asks for, with sizes
GET /evidence/file?path=…   one of those files; only paths on the list are served (no other file can be reached)

The charts on the Evidence page come from /control/runs and /surrogate; these routes give the raw files behind them.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.v2.errors import ApiError
from backend.v2.settings import ROOT

router = APIRouter()

# (group, glob relative to the repository root, what the file is). Globs, so new runs and streets appear by themselves.
GROUPS: list[tuple[str, str, str]] = [
    ("solver_configurations", "data/results/control/*.json", "control run: configuration, provenance, state transitions"),
    ("solver_configurations", "data/surrogate/*/manifest.json", "surrogate data: solver settings and hash, generation config"),
    ("generated_state_splits", "data/surrogate/splits.json", "train, tune, calibrate and test months and days"),
    ("surrogate_artifacts", "ml/models/surrogate/*/manifest.json", "model manifest: supported range, novelty threshold, hashes"),
    ("surrogate_artifacts", "ml/models/surrogate/*/model.npz", "trained model weights"),
    ("surrogate_artifacts", "ml/models/surrogate/README.md", "model card"),
    ("state_of_charge_traces", "data/results/control/*/soc_trace.csv", "battery energy and state of charge, step by step"),
    ("action_logs", "data/results/control/*/actions.jsonl", "every action, status, reason and replan trigger"),
    ("error_latency_results", "ml/reports/surrogate_evaluation.json", "held-out error, misses, latency, end-to-end"),
    ("error_latency_results", "ml/reports/surrogate_bakeoff.json", "model bake-off on the tune split"),
    ("error_latency_results", "ml/reports/surrogate_disagreements.json", "surrogate against solver, with the system's response"),
    ("final_verification_outputs", "data/results/control/*/verification.csv", "before and after power flow at every step"),
    ("final_verification_outputs", "data/results/control/*/summary.md", "run summary with infeasible periods"),
    ("pre_registration", "docs/DECISIONS.md", "method choices written down before each run"),
]


def _listed() -> dict[str, tuple[str, str]]:
    """Relative path -> (group, description) for every evidence file that exists."""
    out: dict[str, tuple[str, str]] = {}
    for group, pattern, what in GROUPS:
        for f in sorted(ROOT.glob(pattern)):
            if f.is_file():
                out.setdefault(f.relative_to(ROOT).as_posix(), (group, what))
    return out


@router.get("/evidence/files")
def files() -> dict:
    groups: dict[str, list[dict]] = {}
    for rel, (group, what) in _listed().items():
        groups.setdefault(group, []).append({"path": rel, "what": what, "bytes": (ROOT / rel).stat().st_size})
    return {"groups": [{"id": g, "files": groups.get(g, [])} for g in dict.fromkeys(g for g, _, _ in GROUPS)]}


@router.get("/evidence/file")
def file(path: str):
    listed = _listed()
    if path not in listed:
        raise ApiError(404, f"{path!r} is not an evidence file", details={"see": "/api/v2/evidence/files"})
    full = (ROOT / path).resolve()
    if ROOT.resolve() not in full.parents:          # belt and braces: the list is built from the repository only
        raise ApiError(404, f"{path!r} is not an evidence file")
    return FileResponse(full, filename=Path(path).name)
