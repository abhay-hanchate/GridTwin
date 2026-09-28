"""Side-by-side simulations for the dashboard: the same day without and with a fix.

Returns compact arrays (one row of bus voltages per 15-minute step) so two maps can
play in sync in the browser.
"""
from engine.actions import ACTIONS
from engine.grid import build_grid, lv_buses
from engine.powerflow import day_inputs, run_day
from engine.scenarios import DEFAULT_DATE, SCENARIOS

ACTIONS_BY_ID = {a.id: a for a in ACTIONS}
STEP_FIELDS = ["max_vm_pu", "min_vm_pu", "pv_kw", "pv_available_kw", "load_kw",
               "inverter_kvar", "battery_kw", "tap_pos"]


def compact(run: dict, bus_ids: list) -> dict:
    """Per-step bus voltages as a matrix plus the per-step headline fields."""
    keys = [str(b) for b in bus_ids]
    return {
        "vm": [[s["bus_vm_pu"][k] for k in keys] if "bus_vm_pu" in s else None for s in run["steps"]],
        "steps": [{f: s.get(f) for f in STEP_FIELDS} | {"unsafe": bool(s["violations"])} for s in run["steps"]],
        "summary": run["summary"],
    }


def worst_bus(run: dict) -> int:
    peak = max((s for s in run["steps"] if "bus_vm_pu" in s), key=lambda s: s["max_vm_pu"])
    return int(max(peak["bus_vm_pu"], key=peak["bus_vm_pu"].get))


def simulate_fix(scenario_id: str, action_id: str, date: str = DEFAULT_DATE) -> dict:
    spec = SCENARIOS[scenario_id]
    action = ACTIONS_BY_ID[action_id]
    inputs = day_inputs(date)

    base_net = build_grid(spec["pv_share"])
    before = run_day(base_net, inputs, band=spec["band"], detail=True)
    net = build_grid(spec["pv_share"])
    after = run_day(net, inputs, band=spec["band"],
                    hook=action.make_hook(net, worst_bus(before), before["limits"]["vm_max_pu"]), detail=True)

    bus_ids = [int(b) for b in lv_buses(base_net)]
    return {
        "scenario_id": scenario_id, "action_id": action_id, "label": action.label, "kind": action.kind,
        "date": date, "band": spec["band"], "limits": before["limits"],
        "times": [s["t"][-5:] for s in before["steps"]],
        "bus_ids": bus_ids,
        "before": compact(before, bus_ids),
        "after": compact(after, bus_ids),
    }
