"""Full-day (96 x 15-minute) power flow and violation detection."""
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd
import pandapower as pp

from engine import config
from engine.grid import LOAD_POWER_FACTOR, lv_buses

TAN_PHI = float(np.tan(np.arccos(LOAD_POWER_FACTOR)))


@dataclass
class DayInputs:
    date: str
    load_kw: pd.DataFrame         # 96 x meters
    pv_kw_per_kwp: pd.Series      # 96
    upstream_vm_pu: pd.Series     # 96


def day_inputs(date: str) -> DayInputs:
    """Real profiles for one day; only meters with a complete day are used."""
    loads = pd.read_parquet(config.PROCESSED_DIR / "load_kw.parquet").loc[date]
    loads = loads.loc[:, loads.notna().all()]
    pv = pd.read_parquet(config.PROCESSED_DIR / "pv_kw_per_kwp.parquet")["pv_kw_per_kwp"].reindex(loads.index).fillna(0)
    vm = pd.read_parquet(config.PROCESSED_DIR / "upstream_vm_pu.parquet")["upstream_vm_pu"]
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
    """Simulate 96 steps. `hook(net, step)` lets a corrective action adjust the grid each step."""
    vmin, vmax = config.BANDS[band]
    lv = lv_buses(net)
    meters = assign_meters(net, inputs.load_kw.columns)
    load_matrix = inputs.load_kw[meters].to_numpy() / 1000          # MW, 96 x houses

    steps, losses_kwh, pv_kwh, curtailed_kwh, battery_kwh = [], 0.0, 0.0, 0.0, 0.0
    for i, t in enumerate(inputs.load_kw.index):
        net.load["p_mw"] = load_matrix[i]
        net.load["q_mvar"] = load_matrix[i] * TAN_PHI
        available = float(inputs.pv_kw_per_kwp.iloc[i]) * net.sgen.sn_mva
        net.sgen["p_mw"] = available
        net.sgen["q_mvar"] = 0.0
        net.ext_grid["vm_pu"] = float(inputs.upstream_vm_pu.iloc[i])
        if hook:
            hook(net, i)
        curtailed_kwh += float((available - net.sgen.p_mw).sum()) * 1000 / 4

        try:
            pp.runpp(net, numba=True, init="results" if i else "auto")
        except pp.LoadflowNotConverged:
            steps.append({"t": t.strftime("%Y-%m-%dT%H:%M"), "solver_failed": True, "violations": []})
            continue

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

        losses_kwh += float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()) * 1000 / 4
        pv_kwh += float(net.res_sgen.p_mw.sum()) * 1000 / 4 if len(net.sgen) else 0.0
        battery_kwh += float(net.res_storage.p_mw.abs().sum()) * 1000 / 4 if len(net.storage) else 0.0
        step = {
            "t": t.strftime("%Y-%m-%dT%H:%M"),
            "max_vm_pu": round(float(vm.max()), 4),
            "min_vm_pu": round(float(vm.min()), 4),
            "trafo_loading_pct": round(trafo_load, 1),
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
        "limits": {"vm_min_pu": vmin, "vm_max_pu": vmax, "loading_max_pct": 100},
        "steps": steps,
        "summary": {
            "max_vm_pu": max(s["max_vm_pu"] for s in ok),
            "min_vm_pu": min(s["min_vm_pu"] for s in ok),
            "violation_steps": sum(1 for s in steps if s["violations"]),
            "solver_failed_steps": len(steps) - len(ok),
            "pv_kwh": round(pv_kwh, 1),
            "curtailed_kwh": round(curtailed_kwh, 1),
            "losses_kwh": round(losses_kwh, 2),
            "battery_throughput_kwh": round(battery_kwh, 1),
            "homes_profiled": int(inputs.load_kw.shape[1]),
        },
        "provenance": {
            "load": "observed: CEEW smart meters, Mathura",
            "voltage": "observed: median CEEW customer voltage, used as upstream voltage",
            "pv": "modeled: pvlib PVWatts on observed Open-Meteo weather",
            "grid": "benchmark: SimBench 1-LV-rural2 with Indian overhead line impedance",
        },
    }
