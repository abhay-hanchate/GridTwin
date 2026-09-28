"""Corrective actions. Each one is a hook applied at every 15-minute step of a full day."""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandapower as pp

VOLT_VAR_PF = 0.9
TAN_VV = float(np.tan(np.arccos(VOLT_VAR_PF)))    # inverter absorbs 0.484 kvar per kW

BATTERY_KW = 50.0
BATTERY_KWH = 200.0
BATTERY_EFF = 0.95                                  # one-way efficiency
SOC_MIN, SOC_MAX = 0.10, 0.90
DISCHARGE_HOURS = range(18, 23)
DROOP_KW_PER_PU = 1500.0                            # 0.01 pu above target -> 15 kW charging
STEP_H = 0.25


@dataclass
class Action:
    id: str
    label: str
    kind: str
    params: dict
    make_hook: Callable[[pp.pandapowerNet, int, float], Callable]
    notes: list = field(default_factory=list)


def _tap(pos: int):
    def make(net, worst_bus, vmax):
        def hook(net, i):
            net.trafo["tap_pos"] = pos
        return hook
    return make


def _volt_var(tap: int = 0):
    def make(net, worst_bus, vmax):
        def hook(net, i):
            net.trafo["tap_pos"] = tap
            net.sgen["q_mvar"] = -net.sgen.p_mw * TAN_VV
        return hook
    return make


def _export_cap(keep: float):
    def make(net, worst_bus, vmax):
        def hook(net, i):
            net.sgen["p_mw"] = net.sgen.p_mw * keep
        return hook
    return make


def _battery():
    """Voltage-aware community battery at the worst bus.

    Charges (absorbs power, pulling voltage down) when the worst bus was near the upper limit
    at the previous step or when solar exceeds demand; discharges in the evening only when
    there is voltage headroom, so it never pushes an already-high voltage further up.
    """
    def make(net, worst_bus, vmax):
        idx = pp.create_storage(net, worst_bus, p_mw=0.0, max_e_mwh=BATTERY_KWH / 1000, name="community battery")
        state = {"soc": 0.5}

        def hook(net, i):
            hour = (i * 15) // 60
            prev_vm = float(net.res_bus.at[worst_bus, "vm_pu"]) if i and len(net.res_bus) else 1.0
            surplus_kw = (net.sgen.p_mw.sum() - net.load.p_mw.sum()) * 1000
            soc = state["soc"]
            room_kw = (SOC_MAX - soc) * BATTERY_KWH / (STEP_H * BATTERY_EFF)
            avail_kw = (soc - SOC_MIN) * BATTERY_KWH * BATTERY_EFF / STEP_H
            # Volt-droop: charge in proportion to how far the worst bus sits above the target,
            # which avoids the on/off swings a weak overhead line would amplify.
            target = vmax - 0.02
            p_kw = 0.0                                                   # >0 charging (pandapower convention)
            if prev_vm > target:
                p_kw = min(BATTERY_KW, room_kw, DROOP_KW_PER_PU * (prev_vm - target))
            elif surplus_kw > 0:
                p_kw = min(BATTERY_KW / 2, surplus_kw, room_kw)
            elif hour in DISCHARGE_HOURS and prev_vm < vmax - 0.05:
                p_kw = -min(BATTERY_KW / 2, avail_kw, DROOP_KW_PER_PU * (vmax - 0.05 - prev_vm))
            soc += (p_kw * BATTERY_EFF if p_kw > 0 else p_kw / BATTERY_EFF) * STEP_H / BATTERY_KWH
            state["soc"] = soc
            net.storage.at[idx, "p_mw"] = p_kw / 1000
        return hook
    return make


ACTIONS = [
    Action("tap_plus1", "Transformer tap +1 (off-load, seasonal)", "tap", {"tap_pos": 1}, _tap(1)),
    Action("tap_plus2", "Transformer tap +2 (off-load, seasonal)", "tap", {"tap_pos": 2}, _tap(2)),
    Action("volt_var", "Inverter Volt/VAR, power factor 0.9", "volt_var", {"pf": VOLT_VAR_PF}, _volt_var(0)),
    Action("tap1_volt_var", "Tap +1 with inverter Volt/VAR", "combined", {"tap_pos": 1, "pf": VOLT_VAR_PF}, _volt_var(1)),
    Action("export_cap_80", "Solar export limited to 80% of output", "curtailment", {"keep": 0.8}, _export_cap(0.8)),
    Action("export_cap_60", "Solar export limited to 60% of output", "curtailment", {"keep": 0.6}, _export_cap(0.6)),
    Action("battery_50kw", "Community battery 50 kW / 200 kWh at the worst bus", "battery",
           {"kw": BATTERY_KW, "kwh": BATTERY_KWH}, _battery()),
]
