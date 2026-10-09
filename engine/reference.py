"""Independent pandapower replay of one real day: the reference the batch engine is checked against."""
from __future__ import annotations

import numpy as np
import pandapower as pp

from engine.grid import build_grid, lv_buses
from engine.powerflow import TAN_PHI, DayInputs, assign_meters


def pandapower_day(inputs: DayInputs, tap: int = 0, pv_share: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """LV bus voltages (96, buses) in pu and transformer loading (96,) in percent, balanced three-phase."""
    net = build_grid(pv_share)
    net.trafo["tap_pos"] = tap
    meters = assign_meters(net, inputs.load_kw.columns)
    load = inputs.load_kw[meters].to_numpy() / 1000
    lv = lv_buses(net)
    voltages, loading = [], []
    for i in range(len(inputs.load_kw)):
        net.load["p_mw"], net.load["q_mvar"] = load[i], load[i] * TAN_PHI
        net.sgen["p_mw"], net.sgen["q_mvar"] = inputs.pv_kw_per_kwp.iloc[i] * net.sgen.sn_mva, 0.0
        net.ext_grid["vm_pu"] = inputs.upstream_vm_pu.iloc[i]
        pp.runpp(net, numba=True, init="results" if i else "auto")
        voltages.append(net.res_bus.loc[lv, "vm_pu"].to_numpy())
        loading.append(float(net.res_trafo.loading_percent.iloc[0]))
    return np.array(voltages), np.array(loading)
