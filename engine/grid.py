"""Feeder model: SimBench rural low-voltage grid adapted to Indian overhead lines."""
import json
import warnings

import numpy as np
import pandapower as pp
import simbench as sb

from engine import config

GRID_CODE = "1-LV-rural2--0-sw"   # 99 houses, 250 kVA transformer (verified)

# ACSR Rabbit overhead conductor, IS 398: DC resistance 0.5524 ohm/km.
# Reactance 0.35 ohm/km is a typical overhead-line value (assumption, see docs/assumptions.md).
OVERHEAD_R_OHM_PER_KM = 0.5524
OVERHEAD_X_OHM_PER_KM = 0.35

LOAD_POWER_FACTOR = 0.95


def build_grid(pv_share: float, seed: int = 42, kwp: float = config.PV_KWP_PER_HOME) -> pp.pandapowerNet:
    """Return the feeder with rooftop solar on `pv_share` (0..1) of the houses."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        net = sb.get_simbench_net(GRID_CODE)

    net.sgen.drop(net.sgen.index, inplace=True)          # remove SimBench's German PV fleet
    net.profiles = {}                                     # we drive the grid with Indian profiles

    lv_lines = net.line.from_bus.map(net.bus.vn_kv) < 1
    net.line.loc[lv_lines, "r_ohm_per_km"] = OVERHEAD_R_OHM_PER_KM
    net.line.loc[lv_lines, "x_ohm_per_km"] = OVERHEAD_X_OHM_PER_KM

    # Without this pandapower silently ignores tap_pos on SimBench transformers.
    net.trafo["tap_changer_type"] = "Ratio"

    rng = np.random.default_rng(seed)
    houses = net.load.bus.to_numpy()
    n_pv = int(round(pv_share * len(houses)))
    for bus in rng.choice(houses, n_pv, replace=False):
        pp.create_sgen(net, int(bus), p_mw=0.0, sn_mva=kwp / 1000, type="PV")
    return net


def lv_buses(net: pp.pandapowerNet):
    return net.bus.index[net.bus.vn_kv < 1]


def topology(net: pp.pandapowerNet) -> dict:
    """Buses with map coordinates, lines and the transformer, for the dashboard."""
    buses = []
    for idx in lv_buses(net):
        lon, lat = json.loads(net.bus.at[idx, "geo"])["coordinates"]
        buses.append({
            "id": int(idx),
            "x": lon, "y": lat,
            "house": bool((net.load.bus == idx).any()),
            "pv": bool((net.sgen.bus == idx).any()),
        })
    lines = [{"id": int(i), "from": int(r.from_bus), "to": int(r.to_bus), "length_m": round(r.length_km * 1000, 1)}
             for i, r in net.line.iterrows()]
    trafo = net.trafo.iloc[0]
    return {"buses": buses, "lines": lines,
            "trafo": {"lv_bus": int(trafo.lv_bus), "sn_kva": float(trafo.sn_mva * 1000)}}
