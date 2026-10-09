"""Full-day (96 x 15-minute) power flow and violation detection."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
import pandapower as pp

from engine import config
from engine.grid import LOAD_POWER_FACTOR, lv_buses
from engine.rules import get_rule
from engine.verdict import binding_limit

TAN_PHI = float(np.tan(np.arccos(LOAD_POWER_FACTOR)))
REVERSE_FLOW_KW = 0.1          # power going back up through the transformer above this counts as reverse flow


@dataclass
class DayInputs:
    date: str
    load_kw: pd.DataFrame         # 96 x meters
    pv_kw_per_kwp: pd.Series      # 96
    upstream_vm_pu: pd.Series     # 96


def day_inputs(date: str, district: str | None = None, processed_dir: Path | None = None) -> DayInputs:
    """Real profiles for one day; only meters with a complete day are used.

    `district=None` reads the Round 1 (legacy) Mathura files so existing results do not move;
    a district name reads the v2 per-district files.
    """
    if district is None:
        base, suffix = config.PROCESSED_DIR, ""
    else:
        base, suffix = (processed_dir or config.PROCESSED_DIR / "v2"), f"_{district}"
    loads = pd.read_parquet(base / f"load_kw{suffix}.parquet").loc[date]
    loads = loads.loc[:, loads.notna().all()]
    pv = pd.read_parquet(base / f"pv_kw_per_kwp{suffix}.parquet")["pv_kw_per_kwp"].reindex(loads.index).fillna(0)
    vm = pd.read_parquet(base / f"upstream_vm_pu{suffix}.parquet")["upstream_vm_pu"]
    vm = vm.reindex(loads.index).interpolate(limit_direction="both")
    if len(loads) != 96 or loads.shape[1] == 0:
        raise ValueError(f"{date}: no complete day of meter data")
    return DayInputs(date, loads, pv, vm)


def assign_meters(net: pp.pandapowerNet, meters, seed: int = 42) -> np.ndarray:
    """Each house gets one real household profile (profiles are reused across houses)."""
    rng = np.random.default_rng(seed)
    return rng.choice(np.asarray(meters), len(net.load))


Hook = Callable[[pp.pandapowerNet, int], None]


def run_day(net: pp.pandapowerNet, inputs: DayInputs, band: str = "10",
            hook: Optional[Hook] = None, detail: bool = True) -> dict:
    """Simulate 96 steps. `hook(net, step)` lets a corrective action adjust the grid each step.

    A hook may carry a `.solve(net, step)` attribute that replaces the plain power flow (smart-inverter
    control needs its own fixed-point iteration).
    """
    rule = get_rule(band)
    vmin, vmax = rule.vmin_pu, rule.vmax_pu
    lv = lv_buses(net)
    meters = assign_meters(net, inputs.load_kw.columns)
    load_matrix = inputs.load_kw[meters].to_numpy() / 1000          # MW, 96 x houses

    steps = []
    losses_kwh = pv_kwh = curtailed_kwh = battery_kwh = reactive_loss_kvarh = inverter_kvarh = 0.0
    max_trafo, reverse_steps = 0.0, 0
    for i, t in enumerate(inputs.load_kw.index):
        stamp = t.strftime("%Y-%m-%dT%H:%M")
        net.load["p_mw"] = load_matrix[i]
        net.load["q_mvar"] = load_matrix[i] * TAN_PHI
        available = float(inputs.pv_kw_per_kwp.iloc[i]) * net.sgen.sn_mva
        net.sgen["p_mw"] = available
        net.sgen["q_mvar"] = 0.0
        net.ext_grid["vm_pu"] = float(inputs.upstream_vm_pu.iloc[i])
        if hook:
            hook(net, i)

        try:
            solve = getattr(hook, "solve", None)
            if solve:
                solve(net, i)
            else:
                pp.runpp(net, numba=True, init="results" if i else "auto")
        except pp.LoadflowNotConverged:
            # A step the solver cannot settle is never safe: it is recorded as a violation, not skipped.
            steps.append({"t": stamp, "solver_failed": True,
                          "violations": [{"type": "solver_failure", "element": "network", "id": 0,
                                          "value": 0.0, "limit": 0.0}]})
            continue
        # Measured after the solve so output trimmed by smart-inverter control is counted.
        curtailed_kwh += float((available - net.sgen.p_mw).sum()) * 1000 / 4

        vm = net.res_bus.loc[lv, "vm_pu"]
        line_load = net.res_line.loading_percent
        trafo_load = float(net.res_trafo.loading_percent.iloc[0])
        violations = [{"type": "overvoltage", "element": "bus", "id": int(b), "value": round(float(v), 4), "limit": vmax}
                      for b, v in vm[vm > vmax].items()]
        violations += [{"type": "undervoltage", "element": "bus", "id": int(b), "value": round(float(v), 4), "limit": vmin}
                       for b, v in vm[vm < vmin].items()]
        violations += [{"type": "line_overload", "element": "line", "id": int(l), "value": round(float(v), 1), "limit": 100}
                       for l, v in line_load[line_load > 100].items()]
        if trafo_load > 100:
            violations.append({"type": "trafo_overload", "element": "trafo", "id": 0, "value": round(trafo_load, 1), "limit": 100})

        # p_hv_mw < 0: power flows from the street back up into the 11 kV network.
        reverse_kw = max(0.0, -float(net.res_trafo.p_hv_mw.iloc[0]) * 1000)
        reverse_steps += reverse_kw > REVERSE_FLOW_KW
        max_trafo = max(max_trafo, trafo_load)
        losses_kwh += float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()) * 1000 / 4
        reactive_loss_kvarh += float(net.res_line.ql_mvar.sum() + net.res_trafo.ql_mvar.sum()) * 1000 / 4
        inverter_kvarh += float(-net.sgen.q_mvar.clip(upper=0).sum()) * 1000 / 4 if len(net.sgen) else 0.0
        pv_kwh += float(net.res_sgen.p_mw.sum()) * 1000 / 4 if len(net.sgen) else 0.0
        battery_kwh += float(net.res_storage.p_mw.abs().sum()) * 1000 / 4 if len(net.storage) else 0.0
        step = {
            "t": stamp,
            "max_vm_pu": round(float(vm.max()), 4),
            "min_vm_pu": round(float(vm.min()), 4),
            "trafo_loading_pct": round(trafo_load, 1),
            "reverse_flow_kw": round(reverse_kw, 2),
            "pv_kw": round(float(net.sgen.p_mw.sum()) * 1000, 2),
            "load_kw": round(float(net.load.p_mw.sum()) * 1000, 2),
            "upstream_vm_pu": round(float(inputs.upstream_vm_pu.iloc[i]), 4),
            # What any corrective action is doing at this step (all zero when no action is applied)
            "pv_available_kw": round(float(available.sum()) * 1000, 2),
            "inverter_kvar": round(float(-net.sgen.q_mvar.sum()) * 1000, 2) if len(net.sgen) else 0.0,
            "battery_kw": round(float(net.storage.p_mw.sum()) * 1000, 2) if len(net.storage) else 0.0,
            "tap_pos": int(net.trafo.tap_pos.iloc[0]),
            "violations": violations,
        }
        if detail:
            step["bus_vm_pu"] = {str(b): round(float(v), 4) for b, v in vm.items()}
            step["line_loading_pct"] = {str(l): round(float(v), 1) for l, v in line_load.items()}
        steps.append(step)

    ok = [s for s in steps if not s.get("solver_failed")]
    return {
        "date": inputs.date,
        "limits": {"vm_min_pu": vmin, "vm_max_pu": vmax, "loading_max_pct": 100, "rule": rule.id},
        "steps": steps,
        "summary": {
            "max_vm_pu": max((s["max_vm_pu"] for s in ok), default=None),
            "min_vm_pu": min((s["min_vm_pu"] for s in ok), default=None),
            "violation_steps": sum(1 for s in steps if s["violations"]),
            "solver_failed_steps": len(steps) - len(ok),
            "reverse_flow_steps": int(reverse_steps),
            "max_trafo_loading_pct": round(max_trafo, 1),
            "reactive_loss_kvarh": round(reactive_loss_kvarh, 2),
            "inverter_kvarh": round(inverter_kvarh, 1),
            "pv_kwh": round(pv_kwh, 1),
            "curtailed_kwh": round(curtailed_kwh, 1),
            "losses_kwh": round(losses_kwh, 2),
            "battery_throughput_kwh": round(battery_kwh, 1),
            "homes_profiled": int(inputs.load_kw.shape[1]),
            "binding_limit": binding_limit(steps),
        },
        "provenance": {
            "load": "observed: CEEW smart meters, Mathura",
            "voltage": "observed: median CEEW customer voltage, used as upstream voltage",
            "pv": "modeled: pvlib PVWatts on observed Open-Meteo weather",
            "grid": "benchmark: SimBench 1-LV-rural2 with Indian overhead line impedance",
        },
    }
