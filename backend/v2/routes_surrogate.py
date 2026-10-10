"""GET /surrogate and /surrogate/disagreements: the power-flow surrogate's evidence (Addition 2).

Read from the files the evaluation wrote (ml/reports/surrogate_*.json); a request never trains, generates or solves.
Every state behind these numbers is simulated, and every verdict in them is the solver's.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request

from backend.v2.errors import ApiError

router = APIRouter()
RULES = ("up_2005", "pm10")
SPLITS = ("base", "boundary", "held_out_tap_mode")
MAX_EXAMPLES = 12
MISSING = "the surrogate evaluation is missing; run python -m scripts.surrogate_train then python -m scripts.surrogate_evaluate"


def _reports(request: Request) -> Path:
    return Path(request.app.state.settings.model_dir).parent / "reports"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApiError(503, MISSING) from exc


def _screener_status(model_dir: Path) -> dict:
    from ml.surrogate.api import load_screener
    try:
        screener = load_screener(model_dir / "surrogate")
    except Exception as exc:                                     # a broken artifact turns the screen off, never the page
        return {"active": False, "streets": [], "reason": f"the artifact could not be loaded: {exc}"}
    if screener is None:
        return {"active": False, "streets": [], "reason": "no usable artifact: every candidate goes to the solver"}
    return {"active": True, "streets": screener.streets, "reason": ""}


def _candidate(kind: str, res: dict, selected: str) -> dict:
    base, boundary = res.get("base", {}).get("regression", {}), res.get("boundary", {}).get("regression", {})
    v = base.get("node_voltage_v") or base.get("v_max_v") or {}
    ld = base.get("line_loading_pts") or base.get("max_line_loading_pts") or {}
    bv = boundary.get("node_voltage_v") or boundary.get("v_max_v") or {}
    gates = res.get("gates_on_base", {})
    return {"kind": kind, "selected": kind == selected, "node_level": "node_voltage_v" in base,
            "voltage_mae_v": v.get("mae"), "voltage_p99_v": v.get("p99"), "loading_mae_pts": ld.get("mae"),
            "loading_p99_pts": ld.get("p99"), "boundary_voltage_p99_v": bv.get("p99"),
            "unsafe_as_safe": {r: res.get("base", {}).get("rules", {}).get(r, {}).get("guarded", {}).get("unsafe_as_safe")
                               for r in RULES},
            "gates_passed": sum(bool(g["passed"]) for g in gates.values()), "gates_total": len(gates)}


def _screening(res: dict) -> list[dict]:
    rows = []
    for split in SPLITS:
        for rule in RULES:
            part = res.get(split, {}).get("rules", {}).get(rule)
            if part:
                keep = ("unsafe_as_safe", "truly_unsafe", "false_rejections", "truly_safe", "false_rejection_rate", "recall", "precision")
                rows.append({"rule": rule, "split": split, "guarded": {k: part["guarded"].get(k) for k in keep},
                             "point": {k: part["point"].get(k) for k in keep}})
    return rows


def _rounds(held: dict, selected: str) -> list[dict]:
    """The chosen model with one margin for every state (round 1) and with margins by predicted value (round 2)."""
    rows = []
    for rnd, cands in sorted(held.get("rounds", {}).items()):
        for rule in RULES:
            g = cands.get(selected, {}).get("base", {}).get("rules", {}).get(rule, {}).get("guarded")
            if g:
                rows.append({"round": int(rnd), "rule": rule, "unsafe_as_safe": g["unsafe_as_safe"], "truly_unsafe": g["truly_unsafe"],
                             "false_rejections": g["false_rejections"], "truly_safe": g["truly_safe"]})
    return rows


def _street(sid: str, ev: dict, bake: dict) -> dict:
    selected = ev.get("selected") or bake.get("selected")
    held = ev.get("heldout", {})
    cands = held.get("candidates", {})
    states = {s: bake.get("states", {}).get(s, {}).get("total") for s in ("train", "tune", "calibrate")}
    states.update(test=held.get("states", {}).get("all"), boundary_test=held.get("states", {}).get("boundary"),
                  out_of_range=sum(v["states"] for v in ev.get("out_of_range", {}).values()) or None)
    at = ev.get("guard", {}).get("at_limits", {})
    return {
        "id": sid, "selected": selected, "selection_reason": bake.get("reason"), "selected_at": bake.get("selected_at_utc"),
        "states": states, "support": ev.get("support"), "shipped_round": held.get("shipped_round", 1),
        "guard_v": [at.get("up_2005", {}).get("v_max_v"), at.get("up_2005", {}).get("v_min_v")],
        "guard_loading_pts": [at.get("line_pts"), at.get("trafo_pts")],
        "rounds": _rounds(held, selected),
        "candidates": [_candidate(k, cands[k], selected) for k in ("ridge", "lgbm", "mlp") if k in cands],
        "gates": [{"name": k, **v} for k, v in cands.get(selected, {}).get("gates_on_base", {}).items()],
        "screening": _screening(cands.get(selected, {})),
        "out_of_range": [{"kind": k, "states": v["states"], "unsupported": v["unsupported"]} for k, v in ev.get("out_of_range", {}).items()],
        "latency": [{"mode": mode, "batch": int(b), "screen_ms_per_state": row.get("screen_ms_per_state"),
                     "solver_ms_per_state": row.get("solver_ms_per_state")}
                    for mode, rows in ev.get("latency", {}).items() for b, row in rows.items()],
        "e1": ev.get("e1_controller_style", {}).get("summary"), "e2": ev.get("e2_fix_tournament", {}).get("summary"),
    }


@router.get("/surrogate")
def surrogate(request: Request) -> dict:
    """The surrogate's accuracy, misses, limits and speed per street, from the pre-registered evaluation."""
    reports = _reports(request)
    ev, bake = _read(reports / "surrogate_evaluation.json"), _read(reports / "surrogate_bakeoff.json")
    dis = _read(reports / "surrogate_disagreements.json")
    return {
        "provenance": ev.get("provenance", "simulated"), "generated_at": ev.get("created_utc"),
        "pre_registration": "docs/DECISIONS.md, Addition 2: power-flow surrogate",
        "screener": _screener_status(Path(request.app.state.settings.model_dir)),
        "streets": [_street(sid, s, bake.get("streets", {}).get(sid, {})) for sid, s in ev.get("streets", {}).items()],
        "disagreements": {"note": dis.get("note"), "counts": dis.get("counts", []), "examples": dis.get("examples", [])[:MAX_EXAMPLES]},
    }


@router.get("/surrogate/disagreements")
def disagreements(request: Request) -> dict:
    """Every logged case where the surrogate and the solver disagreed, and what the system did."""
    return _read(_reports(request) / "surrogate_disagreements.json")
