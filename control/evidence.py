"""Evidence files for one replay: the run as JSON (API and page) plus the plain files the organiser asks for.

data/results/control/<run_id>.json        the whole run (config, provenance, every transition, comparison, timing)
data/results/control/<run_id>/soc_trace.csv        energy and SoC before and after every step, executed battery power
data/results/control/<run_id>/actions.jsonl        planned and executed action, topology, operations, reason, triggers
data/results/control/<run_id>/verification.csv     per step: before and after the action, every checked quantity
data/results/control/<run_id>/summary.md           what passed, what failed, what is simulated
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from control.replay import Replay

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results" / "control"


def write(replay: Replay, out: Path = OUT) -> Path:
    d = replay.to_dict()
    run_id = d["config"]["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
    folder = out / run_id
    folder.mkdir(exist_ok=True)
    recs = d["records"]
    with (folder / "soc_trace.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["step", "time", "energy_before_kwh", "energy_after_kwh", "soc_before", "soc_after", "battery_kw",
                    "baseline_battery_kw", "baseline_energy_after_kwh"])
        for i, r in enumerate(recs):
            w.writerow([r["step"], r["time"], r["energy_before_kwh"], r["energy_after_kwh"], r["soc_before"],
                        r["soc_after"], r["action"]["battery_kw"], d["baseline"]["battery_kw"][i],
                        d["baseline"]["energy_kwh"][i + 1]])
    with (folder / "actions.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps({k: r[k] for k in ("step", "time", "status", "reason", "action", "replan_triggers",
                                                  "topology_before", "topology_after", "operations_used",
                                                  "operations_left", "planner", "plan_horizon")}) + "\n")
    cols = ["safe", "v_max_v", "v_min_v", "line_max_pct", "trafo_pct", "vuf_pct", "margin_v", "severity"]
    with (folder / "verification.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["step", "time", "status"] + [f"before_{c}" for c in cols] + [f"after_{c}" for c in cols]
                   + ["after_reasons", "baseline_safe", "baseline_v_max_v", "baseline_v_min_v"])
        for i, r in enumerate(recs):
            w.writerow([r["step"], r["time"], r["status"]] + [r["before"][c] for c in cols]
                       + [r["after"][c] for c in cols] + ["; ".join(r["after"]["reasons"]), d["baseline"]["safe"][i],
                                                         d["baseline"]["v_max_v"][i], d["baseline"]["v_min_v"][i]])
    (folder / "summary.md").write_text(summary_md(d), encoding="utf-8")
    return folder


def summary_md(d: dict) -> str:
    s, c, t = d["summary"], d["config"], d["timing"]
    periods = s["infeasible_periods"]
    lines = [
        f"# {c['title'] or c['run_id']}",
        "",
        f"Street `{c['network_id']}`, rule `{c['rule_id']}`, {c['date']}, quarter hours {c['start']} to {c['end'] - 1}, "
        f"horizon {c['horizon']}. Battery {c['battery_kw']} kW / {c['battery_kwh']} kWh at node "
        f"{d['provenance']['battery_node']}, starting at {c['soc_start']:.0%}.",
        "",
        f"- Observations: {d['provenance']['observations']}.",
        f"- Perturbations: {', '.join(p['label'] or p['kind'] for p in c['perturbations']) or 'none'}.",
        f"- Tap: {d['provenance']['tap']}.",
        "",
        "| | Unsafe quarter hours |",
        "|---|---|",
        f"| No control | {s['unsafe_steps_without_control']} of {s['steps']} |",
        f"| Reactive battery rule, same observations | {s['baseline_unsafe_steps']} of {s['steps']} |",
        f"| Receding-horizon controller | {s['unsafe_steps']} of {s['steps']} |",
        "",
        f"Statuses: {', '.join(f'{k} {v}' for k, v in s['statuses'].items() if v)}. Curtailed {s['curtailed_kwh']} kWh; "
        f"battery throughput {s['throughput_kwh']} kWh (reactive rule {s['baseline_throughput_kwh']} kWh); SoC "
        f"{s['soc_min']:.0%} to {s['soc_max']:.0%}; switching operations {s['operations_used']}; fallbacks "
        f"{s['fallbacks']}.",
        "",
        "Infeasible periods (no permitted action verified safe):" if periods else "No infeasible period.",
    ]
    for p in periods:
        lines.append(f"- {p['from']} to {p['until']} ({p['steps']} steps, {', '.join(p['statuses'])}): {p['first_reason']}")
    lines += ["", f"Timing: total {t['total_s']} s; per step p50 {t['step_p50_s']} s, p95 {t['step_p95_s']} s.", "",
              "Only steps marked verified_safe passed every declared check in the real three-phase solver at the "
              "observed step. Observations are simulated; this is not a field test.", ""]
    return "\n".join(lines)
