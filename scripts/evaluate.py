"""P10.4: collect every gate and headline into data/results/results.json, the single source of truth for numbers.

Usage:  python -m scripts.evaluate [--skip-parity]

Each gate records what was measured, the threshold, a status (pass, fail, conditional, not_run or missing), its
provenance, the file it was read from and the command that produced it. Gates are read from the reports the
pipeline already wrote; only G1 (engine parity) is recomputed here (about 20 s). A failed gate is written as failed:
the Proof page shows it, it is never hidden. docs/generated/proof.md is generated from the same file.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results" / "results.json"
PROOF = ROOT / "docs" / "generated" / "proof.md"
STATUSES = ("pass", "fail", "conditional", "not_run", "missing")


def _read(root: Path, rel: str) -> dict | None:
    try:
        return json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gate(gid: str, name: str, status: str, *, measured=None, threshold: str = "", provenance: str = "",
         source: str = "", command: str = "", note: str = "") -> dict:
    assert status in STATUSES, status
    return {"gate": gid, "name": name, "status": status, "passed": {"pass": True, "fail": False}.get(status),
            "measured": measured, "threshold": threshold, "provenance": provenance, "source": source,
            "command": command, "note": note}


def g1_parity(skip: bool) -> dict:
    name, threshold = "Engine parity with pandapower", "max voltage difference <= 0.1% and at least 10x faster"
    if skip:
        return gate("G1", name, "not_run", threshold=threshold, note="skipped with --skip-parity")
    import numpy as np

    from engine.dayinputs import scenarios_from_legacy
    from engine.grid import build_grid
    from engine.network import from_pandapower
    from engine.powerflow import day_inputs
    from engine.reference import pandapower_day
    from engine.solver import DaySolver
    inputs = day_inputs("2019-05-15")
    net = from_pandapower(build_grid(1.0), phases="round_robin")
    solver = DaySolver(net, asymmetric=False)
    scn = scenarios_from_legacy(inputs, net)
    solver.solve(scn)
    t = time.perf_counter()
    res = solver.solve(scn)
    t_pgm = time.perf_counter() - t
    t = time.perf_counter()
    u_ref, trafo_ref = pandapower_day(inputs)
    t_pp = time.perf_counter() - t
    dv = float(np.abs(res.u_pu[0, :, :, 0] - u_ref).max())
    measured = {"max_voltage_diff_pct": round(dv * 100, 4), "max_voltage_diff_v": round(dv * 230, 3),
                "max_trafo_loading_diff_pts": round(float(np.abs(res.trafo_loading_pct[0] - trafo_ref).max()), 3),
                "day_seconds_pgm": round(t_pgm, 3), "day_seconds_pandapower": round(t_pp, 2),
                "speedup": round(t_pp / t_pgm, 1)}
    ok = dv * 100 <= 0.1 and t_pp / t_pgm >= 10
    return gate("G1", name, "pass" if ok else "fail", measured=measured, threshold=threshold,
                provenance="benchmark: SimBench street, 15 May 2019", command="python -m scripts.evaluate")


def g2_g3(root: Path) -> list[dict]:
    rel = "ml/reports/solar_v2.json"
    d = _read(root, rel)
    if d is None:
        return [gate("G2", "Weather-model availability", "missing", source=rel),
                gate("G3", "Solar v2 beats Round 1", "missing", source=rel)]
    avail = {a["model"]: a["passes"] for a in d["availability"]}
    used = d["nwp_models_used"]
    s = d["scores_2025"]
    return [
        gate("G2", "Weather-model availability", "pass" if used and all(avail[m] for m in used) else "fail",
             measured={"models_used": used, "dropped": sorted(m for m, ok in avail.items() if not ok)},
             threshold=">= 95% non-null hours from the first valid hour and in the test year, per model",
             provenance="observed: Open-Meteo previous-runs API", source=rel, command="python -m ml.solar_v2"),
        gate("G3", "Solar v2 beats Round 1", "pass" if s["gate_g3_passes"] else "fail",
             measured={"mae_p50": s["mae_p50"], "round1_mae": 0.0396, "coverage_80": s["p10_p90_coverage"],
                       "wis": s.get("wis")},
             threshold="MAE below 0.0396 kW/kWp on the identical 2025 daylight mask",
             provenance="modeled vs an ERA5-driven PV proxy (not rooftop meters)", source=rel,
             command="python -m ml.solar_v2"),
    ]


def g4(root: Path) -> dict:
    rel = "ml/reports/demand_v2.json"
    d = _read(root, rel)
    if d is None:
        return gate("G4", "Demand v2 skill and coverage", "missing", source=rel)
    g = d["gate_g4"]
    return gate("G4", "Demand v2 skill and coverage", "pass" if g["passed"] else "fail",
                measured={"skill_vs_best_baseline": g["skill_vs_best_baseline"], "coverage_80": g["coverage"]},
                threshold="skill >= 10% against the best baseline and coverage 78-82% (strict variant, Mathura 2021)",
                provenance="observed: CEEW meters", source=rel, command="python -m ml.demand_v2",
                note="Failed and kept failed by the owner: no AI-improvement claim for demand.")


def g5(root: Path) -> dict:
    rel = "data/results/engine_sensitivity.json"
    d = _read(root, rel)
    if d is None:
        return gate("G5", "Unbalanced engine converges; zero-sequence sensitivity", "missing", source=rel)
    return gate("G5", "Unbalanced engine converges; zero-sequence sensitivity",
                "pass" if d["gate_g5_converged"] else "fail",
                measured={"peak_range_v": d["zero_sequence_peak_range_v"], "balanced_peak_v": d["balanced"]["max_voltage_v"],
                          "phase_modes_peak_v": {k: v["max_voltage_v"] for k, v in d["phase_modes"].items()}},
                threshold=">= 99% of steps converge for every phase mode and r0/x0 ratio 2-4",
                provenance="benchmark: SimBench street, 15 May 2019", source=rel,
                command="python -m scripts.engine_sensitivity")


def g6_g7(root: Path) -> list[dict]:
    g6_src, g7_src = "docs/DATA_SOURCES.md", "docs/DECISIONS.md"
    g6_text = (root / g6_src).read_text(encoding="utf-8") if (root / g6_src).is_file() else ""
    g7_text = (root / g7_src).read_text(encoding="utf-8") if (root / g7_src).is_file() else ""
    g6 = (gate("G6", "Data and API licences permit the use", "conditional", source=g6_src,
               measured="Open-Meteo free API: non-commercial use only",
               threshold="licences permit the intended use",
               note="Demo and research fit; a DISCOM deployment needs a paid plan or another licensed source.")
          if "non-commercial use only" in g6_text else gate("G6", "Data and API licences permit the use", "missing", source=g6_src))
    g7 = (gate("G7", "Measured-plant yield calibration", "not_run", source=g7_src,
               measured="outcome (b): IEEE DataPort needs a login",
               threshold="plant file readable with stated capacity",
               note="PV keeps the 14% system-loss assumption: yield not calibrated against measured data.")
          if "outcome is **(b)**" in g7_text else gate("G7", "Measured-plant yield calibration", "missing", source=g7_src))
    return [g6, g7]


def g8(root: Path) -> dict:
    rows, statuses = {}, []
    for rule in ("pm10", "up_2005"):
        rel = f"data/results/reliability_mathura_{rule}.json"
        d = _read(root, rel)
        if d is None:
            statuses.append("missing")
            continue
        rows[rule] = {"brier": d["brier"], "brier_base_rate": d["brier_climatology"], "brier_skill": d["brier_skill"],
                      "days": d["days"], "observed_unsafe_share": d["observed_unsafe_share_of_steps"],
                      "unsafe_hours_predicted": d["unsafe_hours"]["predicted_mean"],
                      "unsafe_hours_observed": d["unsafe_hours"]["observed_mean"]}
        cal = _read(root, f"data/results/risk_calibration_{rule}.json")
        if cal:                                   # the recalibrated values are what the API serves
            rows[rule]["brier_skill_calibrated"] = cal["held_out_test"]["skill_calibrated"]
            rows[rule]["calibrated_reliable"] = cal["reliable"]
        skill = rows[rule].get("brier_skill_calibrated", d["brier_skill"])
        statuses.append("pass" if (skill or 0) > 0 else "fail")
    status = "missing" if not rows else ("pass" if all(s == "pass" for s in statuses) else "fail")
    return gate("G8", "Risk probabilities are reliable", status, measured=rows,
                threshold="Brier skill > 0 against the base rate, on every rule",
                provenance="observed: replay of held-out 2021 days", source="data/results/reliability_mathura_*.json",
                command="python -m scripts.run_reliability --rule <rule>",
                note="Judged on the isotonic-recalibrated values the API serves (fitted on 2020-05..12, tested on "
                     "held-out 2021). The 2021 window is January-February only and about 5 V above the training years; "
                     "under +/-6% almost every step is unsafe, so nothing beats the base rate there.")


def bakeoffs(root: Path) -> list[dict]:
    out = []
    for f in sorted((root / "data" / "results").glob("bakeoff_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        winner = d.get("winner")
        if isinstance(winner, dict):
            winner = {k: v.get("winner") if isinstance(v, dict) else v for k, v in winner.items()}
        out.append({"component": d.get("component", f.stem[8:]), "winner": winner, "rule": d.get("rule"),
                    "split": d.get("split"), "git_hash": d.get("git_hash"), "source": f.relative_to(root).as_posix()})
    return out


def headlines(root: Path) -> dict:
    out = {}
    t = _read(root, "data/results/tournament_headline.json")
    if t:
        out["tournament_15_may_2019"] = {r: t[r]["verdict"]["message"] for r in ("pm10", "up_2005") if r in t}
    index = _read(root, "data/results/v2/index.json")
    if index:
        demo = []
        for e in index["entries"]:
            res = _read(root, f"data/results/v2/{e['key']}.json") or {}
            row = {"route": e["route"], "date": e["date"], "day_type": e.get("day_type"), "rule": e["rule"]}
            if e["route"] == "risk":
                row.update(level=res.get("level"), expected_unsafe_hours=res.get("expected_unsafe_hours"))
            elif e["route"] == "fixes":
                v = res.get("verdict", {})
                row.update(safe_action_found=v.get("safe_action_found"), recommended=v.get("recommended"),
                           closest=v.get("closest"))
            elif e["route"] == "hosting":
                row.update(without_fix=res.get("without_fix", {}).get("adoption_share"),
                           with_volt_var=res.get("with_volt_var", {}).get("adoption_share"))
            demo.append(row)
        out["demo"] = {"code_version": index.get("code_version"), "results": demo}
    return out


def evaluate(root: Path = ROOT, skip_parity: bool = False) -> dict:
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True,
                                           stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        git_hash = "unknown"
    gates = [g1_parity(skip_parity), *g2_g3(root), g4(root), g5(root), *g6_g7(root), g8(root)]
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "git_hash": git_hash,
            "summary": {s: sum(g["status"] == s for g in gates) for s in STATUSES},
            "gates": gates, "bakeoffs": bakeoffs(root), "headlines": headlines(root)}


def proof_markdown(results: dict) -> str:
    lines = ["# Proof: gates and headline results", "",
             f"Generated {results['generated_at'][:16]} UTC from `data/results/results.json` (git {results['git_hash']}). "
             "Do not edit by hand: run `python -m scripts.evaluate`.", "",
             "| Gate | What | Status | Measured | Threshold |", "| --- | --- | --- | --- | --- |"]
    for g in results["gates"]:
        measured = json.dumps(g["measured"]) if isinstance(g["measured"], (dict, list)) else (g["measured"] or "")
        lines.append(f"| {g['gate']} | {g['name']} | **{g['status']}** | {measured} | {g['threshold']} |")
    notes = [f"- **{g['gate']}**: {g['note']}" for g in results["gates"] if g["note"]]
    if notes:
        lines += ["", "## Notes", "", *notes]
    if results["bakeoffs"]:
        lines += ["", "## Bake-offs", "", "| Component | Winner | Record |", "| --- | --- | --- |"]
        lines += [f"| {b['component']} | {b['winner']} | `{b['source']}` |" for b in results["bakeoffs"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-parity", action="store_true")
    results = evaluate(skip_parity=ap.parse_args().skip_parity)
    OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(proof_markdown(results), encoding="utf-8")
    print(json.dumps(results["summary"]), {g["gate"]: g["status"] for g in results["gates"]})


if __name__ == "__main__":
    main()
