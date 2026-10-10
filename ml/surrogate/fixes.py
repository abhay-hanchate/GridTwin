"""Requirement 2.3 on the existing whole-day fix tournament: screen first, then let the solver decide.

Each candidate becomes one OperatingState per scenario and quarter hour (what the solver would be given). A candidate
whose screen says *clearly unsafe* (even the optimistic bound breaks a limit) at some step is not solved; every other
candidate is solved exactly as engine.fixes.tournament does. Only solver outcomes are ranked or recommended.
Candidates the contract cannot describe (the battery droop policy, a fixed non-unity power factor, a changed inverter
rating) are always solved; phase moves and switching are described and the screener refuses them.
"""
from __future__ import annotations

import time

import numpy as np

from engine.fixes import catalog
from engine.fixes.base import Candidate, evaluate_candidate
from engine.rules import VoltageRule
from engine.types import DayScenarioBatch, Network
from engine.verdict import build_verdict
from ml.surrogate.api import OperatingState, Screener


def _mode(controls) -> str:
    vv, vw = controls.volt_var is not None, controls.volt_watt is not None
    return {(False, False): "fixed_pf", (True, False): "volt_var", (False, True): "volt_watt", (True, True): "volt_var_watt"}[(vv, vw)]


def candidate_states(c: Candidate, scn: DayScenarioBatch, street: str) -> tuple[list[OperatingState] | None, str]:
    """One state per (scenario, step), or (None, reason) when the contract cannot describe the candidate."""
    ctl = c.controls
    if c.battery is not None or ctl.battery is not None:
        return None, "the battery droop policy reacts to the previous step's solved voltage, so it is solved step by step"
    if ctl.pf_fixed is not None:
        return None, "a fixed non-unity power factor is not in the screening contract"
    if ctl.inverter_s_factor != 1.0:
        return None, "a changed inverter rating is not in the screening contract"
    net = c.network
    s, t = scn.shape
    kwp = net.house_kwp
    avail = scn.pv_per_kwp[:, :, None] * kwp[None, None, :]                              # (S, T, H)
    p_cap = avail * (ctl.curtail_keep if ctl.curtail_keep is not None else 1.0)
    if ctl.export_limit_kw is not None:
        lim = np.broadcast_to(np.asarray(ctl.export_limit_kw, float), (t, net.n_homes))
        p_cap = np.minimum(p_cap, scn.load_kw + lim[None])
    ends = tuple((int(a), int(b)) for a, b in zip(net.line_from, net.line_to))
    phases, mode = tuple(int(p) for p in net.house_phase), _mode(ctl)
    out = []
    for i in range(s):
        for j in range(t):
            out.append(OperatingState(
                network_id=street, line_ends=ends, load_kw=scn.load_kw[i, j], pv_kw=p_cap[i, j],
                upstream_pu=float(scn.upstream_pu[i, j]), tap_pos=int(ctl.tap_pos), inverter_mode=mode,
                house_phase=phases, pv_kwp=kwp, ambient_c=None if scn.ambient_c is None else float(scn.ambient_c[i, j])))
    return out, ""


def screen_candidate(screener: Screener, c: Candidate, scn: DayScenarioBatch, street: str, rule: VoltageRule) -> dict:
    states, reason = candidate_states(c, scn, street)
    if states is None:
        return {"status": "unsupported", "reason": reason, "states": 0, "supported_states": 0, "risky_states": 0,
                "clearly_unsafe_states": 0}
    d = screener.screen_detail(states, rule)
    sup = d["supported"]
    reasons = sorted({r for r in d["reason"] if r})
    with np.errstate(invalid="ignore"):
        g = d["guarded"][sup]
    return {"status": "supported" if sup.all() else ("partly supported" if sup.any() else "unsupported"),
            "reason": reasons[0] if reasons else "", "states": len(states), "supported_states": int(sup.sum()),
            "risky_states": int(d["risky"].sum()), "clearly_unsafe_states": int(d["clearly_unsafe"].sum()),
            "guarded_v_max_pu": round(float(g[:, 0].max()), 4) if sup.any() else None,
            "guarded_v_min_pu": round(float(g[:, 1].min()), 4) if sup.any() else None,
            "screened_safe": bool(sup.all() and not d["risky"].any())}


def assisted_tournament(network: Network, scn: DayScenarioBatch, rule: VoltageRule, screener: Screener | None, *,
                        street: str | None = None, candidates: list[Candidate] | None = None,
                        include_battery: bool = True, include_switching: bool = True) -> dict:
    """The tournament with screening (or, with screener=None, the plain solver-only tournament, timed the same way)."""
    street = street or network.provenance.get("archetype", network.name)
    t0 = time.perf_counter()
    before = evaluate_candidate(Candidate("none", "Do nothing", "none", network), scn, rule)
    cands = candidates if candidates is not None else catalog.build(network, scn, rule, include_battery=include_battery,
                                                                     include_switching=include_switching)
    t_build = time.perf_counter() - t0
    rows, t_screen = [], 0.0
    for c in cands:
        row = {"id": c.id, "label": c.label, "kind": c.kind, "screen": None, "skipped": False}
        if screener is not None:
            t1 = time.perf_counter()
            row["screen"] = screen_candidate(screener, c, scn, street, rule)
            t_screen += time.perf_counter() - t1
            row["skipped"] = row["screen"]["clearly_unsafe_states"] > 0
        rows.append(row)
    t_solver, outcomes = 0.0, {}

    def solve(c, row):
        nonlocal t_solver
        t1 = time.perf_counter()
        o = evaluate_candidate(c, scn, rule)
        t_solver += time.perf_counter() - t1
        outcomes[c.id] = o
        row.update(verified=bool(o.acceptable), unsafe_steps=int(o.unsafe_steps))

    for c, row in zip(cands, rows):
        if row["skipped"]:
            row.update(verified=None, unsafe_steps=None)
        else:
            solve(c, row)
    # A "no safe action" verdict never rests on the screen: if nothing solved is safe, the skipped candidates are
    # solved too (the screen may only reorder or skip work when a verified safe action exists).
    fallback = 0
    if not any(o.acceptable for o in outcomes.values()):
        for c, row in zip(cands, rows):
            if row["skipped"]:
                solve(c, row)
                row["skipped"], row["solved_as_fallback"] = False, True
                fallback += 1
    safe = sorted((o for o in outcomes.values() if o.acceptable), key=lambda o: o.cost)
    rest = sorted((o for o in outcomes.values() if not o.acceptable), key=lambda o: (o.unsafe_steps, o.cost))
    as_result = lambda o: {"action_id": o.candidate.id, "label": o.candidate.label,  # noqa: E731
                           "remaining_violation_steps": o.unsafe_steps, "cost": {"curtailed_kwh": o.summary["curtailed_kwh"]},
                           "binding_limit": o.binding_limit}
    results = [as_result(o) for o in safe + rest]
    verdict = build_verdict(results, results[:len(safe)])
    disagreements = [{"candidate": r["id"], "screen": "safe at every step", "solver": f"unsafe at {r['unsafe_steps']} steps",
                      "response": "the solver's verdict stands; the candidate is not recommended"}
                     for r in rows if r["screen"] and r["screen"].get("screened_safe") and r["verified"] is False]
    return {"rule": rule.id, "baseline_unsafe_steps": before.unsafe_steps, "candidates": rows,
            "safe_ranked": [o.candidate.id for o in safe], "best": safe[0].candidate.id if safe else None,
            "safe_action_found": verdict["safe_action_found"], "disagreements": disagreements,
            "timing": {"build_s": round(t_build, 3), "screen_s": round(t_screen, 3), "solver_s": round(t_solver, 3),
                       "total_s": round(t_build + t_screen + t_solver, 3)},
            "solved_candidates": len(outcomes), "skipped_candidates": sum(r["skipped"] for r in rows),
            "fallback_solved": fallback, "closest": verdict.get("closest")}
