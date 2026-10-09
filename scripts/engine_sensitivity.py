"""Gate G5 evidence: convergence and the zero-sequence sensitivity of the unbalanced engine.

Usage: python -m scripts.engine_sensitivity [--date 2019-05-15] [--out data/results/engine_sensitivity.json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import warnings
from pathlib import Path

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import PHASE_MODES, assign_phases, from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.violations import evaluate, summarise

RATIOS = (2.0, 3.0, 4.0)
RULE = "pm10"


def run(date: str) -> dict:
    warnings.filterwarnings("ignore")
    pp_net, rule = build_grid(1.0), get_rule(RULE)
    base = from_pandapower(pp_net, phases="round_robin")
    scn = scenarios_from_legacy(day_inputs(date), base)

    def row(res) -> dict:
        s = summarise(res, evaluate(res, rule))
        return {"max_voltage_v": round(s["max_vm_pu"] * 230, 1), "unsafe_steps": s["violation_steps"],
                "max_vuf_pct": s["max_vuf_pct"], "converged_share": float(res.converged.mean())}

    out = {"date": date, "rule": RULE, "balanced": row(DaySolver(base, asymmetric=False).solve(scn)), "phase_modes": {}, "zero_sequence": []}
    for mode in PHASE_MODES:
        out["phase_modes"][mode] = row(DaySolver(base.with_phases(assign_phases(base.n_homes, mode)), asymmetric=True).solve(scn))
    for r0, x0 in itertools.product(RATIOS, RATIOS):
        net = from_pandapower(pp_net, phases="random", r0_ratio=r0, x0_ratio=x0)
        out["zero_sequence"].append({"r0_ratio": r0, "x0_ratio": x0, **row(DaySolver(net, asymmetric=True).solve(scn))})
    peaks = [z["max_voltage_v"] for z in out["zero_sequence"]]
    out["zero_sequence_peak_range_v"] = [min(peaks), max(peaks)]
    out["gate_g5_converged"] = all(z["converged_share"] >= 0.99 for z in out["zero_sequence"]) and \
        all(m["converged_share"] >= 0.99 for m in out["phase_modes"].values())
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2019-05-15")
    ap.add_argument("--out", default="data/results/engine_sensitivity.json")
    args = ap.parse_args()
    result = run(args.date)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("balanced", "zero_sequence_peak_range_v", "gate_g5_converged")}, indent=2))
