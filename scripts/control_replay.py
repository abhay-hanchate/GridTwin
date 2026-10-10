"""Run the Addition 1 demonstrations and write their evidence (control.evidence).

Usage:  python -m scripts.control_replay                 every fixture
        python -m scripts.control_replay forecast_error  one fixture
        python -m scripts.control_replay --near-limit    also the near-limit sweep (after forecast_error exists)
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from control import evidence
from control.fixtures import FIXTURES
from control.replay import run


def near_limit(run_id: str = "forecast_error", factors=(0.9, 0.95, 1.0, 1.02, 1.05, 1.1)) -> dict:
    """At the step of `run_id` closest to a voltage limit after control, scale the observed solar and replay the
    executed action in the real solver: the limit is crossed on one side and kept on the other."""
    from backend.v2 import compute
    from control.execution import Executor
    from control.forecast import make_world
    from control.verify import physical_check
    d = json.loads((evidence.OUT / f"{run_id}.json").read_text(encoding="utf-8"))
    cfg = FIXTURES[run_id]
    rec = min((r for r in d["records"] if r["status"] == "verified_safe" and r["after"]["margin_v"] is not None),
              key=lambda r: r["after"]["margin_v"])
    net, rule = compute.network(cfg.network_id), compute.rule(cfg.rule_id)
    world = make_world(cfg.date, net, n=cfg.n_scenarios, truth_quantile=cfg.truth_quantile, perturbations=cfg.perturbations)
    ex = Executor(net, battery_node=d["provenance"]["battery_node"], battery_kw_max=cfg.battery_kw, tap_pos=cfg.tap_pos)
    obs = world.observed.take([rec["step"]] * len(factors))
    obs.pv_per_kwp[0, :] *= np.array(factors)
    a = rec["action"]
    res = ex.solve(obs, np.full(len(factors), a["battery_kw"]), np.tile(a["keep"], (len(factors), 1)), a["topology_id"])
    chk = physical_check(res, rule)
    out = {"run_id": run_id, "step": rec["step"], "time": rec["time"], "action": a, "limit_v": rule.vmax_v,
           "provenance": "simulated observation scaled; the executed action held fixed",
           "rows": [{"solar_factor": f, "v_max_v": round(float(chk.v_max_v[0, i]), 2), "safe": bool(chk.safe[0, i]),
                     "margin_v": round(float(chk.margin_v[0, i]), 2)} for i, f in enumerate(factors)]}
    (evidence.OUT / "near_limit.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="*", default=list(FIXTURES))
    ap.add_argument("--near-limit", action="store_true")
    args = ap.parse_args()
    index = {}
    for name in args.fixtures:
        r = run(FIXTURES[name])
        folder = evidence.write(r)
        s = r.summary
        print(f"{name}: unsafe {s['unsafe_steps']} (reactive {s['baseline_unsafe_steps']}, none "
              f"{s['unsafe_steps_without_control']}) of {s['steps']}; {r.timing['total_s']} s -> {folder}")
    for f in sorted(evidence.OUT.glob("*.json")):
        if f.stem in FIXTURES:
            d = json.loads(f.read_text(encoding="utf-8"))
            index[f.stem] = {"title": d["config"]["title"], "network_id": d["config"]["network_id"],
                             "rule_id": d["config"]["rule_id"], "summary": d["summary"], "timing": d["timing"]}
    (evidence.OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    if args.near_limit:
        print(json.dumps(near_limit(), indent=1))


if __name__ == "__main__":
    main()
