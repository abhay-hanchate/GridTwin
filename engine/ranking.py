"""Evaluate every action over the full day, keep only those that are safe at all 96 steps, rank them."""
from engine.actions import ACTIONS
from engine.grid import build_grid
from engine.powerflow import day_inputs, run_day
from engine.scenarios import DEFAULT_DATE, SCENARIOS


def _worst_bus(result: dict) -> int:
    peak = max((s for s in result["steps"] if "bus_vm_pu" in s), key=lambda s: s["max_vm_pu"])
    return int(max(peak["bus_vm_pu"], key=peak["bus_vm_pu"].get))


def _snapshot(summary: dict) -> dict:
    return {k: summary[k] for k in ("max_vm_pu", "min_vm_pu", "violation_steps")}


def _reasons(before: dict, after: dict) -> list:
    reasons = []
    if after["violation_steps"] == 0:
        reasons.append("clears_all_violations")
    elif after["violation_steps"] < before["violation_steps"]:
        reasons.append("reduces_violations")
    else:
        reasons.append("does_not_help")
    if after["max_vm_pu"] < before["max_vm_pu"] - 0.005:
        reasons.append("lowers_peak_voltage")
    if after["min_vm_pu"] < before["min_vm_pu"] - 0.005:
        reasons.append("lowers_evening_voltage")
    if after.get("curtailed_kwh", 0) > 0:
        reasons.append("wastes_solar")
    return reasons


def evaluate_actions(scenario_id: str, date: str = DEFAULT_DATE) -> dict:
    spec = SCENARIOS[scenario_id]
    inputs = day_inputs(date)
    base = run_day(build_grid(spec["pv_share"]), inputs, band=spec["band"], detail=True)
    before = _snapshot(base["summary"])
    worst = _worst_bus(base)

    results = []
    for action in ACTIONS:
        net = build_grid(spec["pv_share"])
        hook = action.make_hook(net, worst, base["limits"]["vm_max_pu"])
        run = run_day(net, inputs, band=spec["band"], hook=hook, detail=False)
        s = run["summary"]
        after = {**_snapshot(s), "curtailed_kwh": s["curtailed_kwh"]}
        acceptable = s["violation_steps"] == 0 and s["solver_failed_steps"] == 0
        results.append({
            "action_id": action.id, "label": action.label, "kind": action.kind, "params": action.params,
            "acceptable": acceptable,
            "remaining_violation_steps": s["violation_steps"],
            "before": before, "after": _snapshot(s),
            "cost": {"curtailed_kwh": s["curtailed_kwh"], "losses_kwh": s["losses_kwh"],
                     "battery_throughput_kwh": s["battery_throughput_kwh"]},
            "reason_codes": _reasons(before, after),
        })

    safe = sorted((r for r in results if r["acceptable"]),
                  key=lambda r: (r["cost"]["curtailed_kwh"], r["cost"]["battery_throughput_kwh"],
                                 r["cost"]["losses_kwh"]))
    for rank, r in enumerate(safe, 1):
        r["rank"] = rank
    for r in results:
        r.setdefault("rank", None)

    best_partial = min(results, key=lambda r: (r["remaining_violation_steps"], r["cost"]["curtailed_kwh"]))
    verdict = {
        "safe_action_found": bool(safe),
        "recommended": safe[0]["action_id"] if safe else None,
        "message": (f"Recommended: {safe[0]['label']}" if safe else
                    f"No safe action: every option leaves violations. Closest is "
                    f"'{best_partial['label']}' with {best_partial['remaining_violation_steps']} unsafe steps."),
    }
    ordered = safe + sorted((r for r in results if not r["acceptable"]), key=lambda r: r["remaining_violation_steps"])
    return {"scenario_id": scenario_id, "date": date, "band": spec["band"], "worst_bus": worst,
            "before": before, "actions": ordered, "verdict": verdict}
