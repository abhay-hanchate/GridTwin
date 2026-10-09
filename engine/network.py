"""Build the canonical Network from a pandapower net, and assign single-phase homes to phases."""
from __future__ import annotations

import json

import numpy as np
import pandapower as pp

from engine.types import Network, TrafoSpec

PHASE_MODES = ("random", "round_robin", "all_a")


def assign_phases(n: int, mode: str = "random", seed: int = 42) -> np.ndarray:
    if mode == "round_robin":
        return np.arange(n) % 3
    if mode == "all_a":
        return np.zeros(n, dtype=int)
    if mode == "random":
        return np.random.default_rng(seed).integers(0, 3, n)
    raise ValueError(f"unknown phase mode {mode!r}; choose from {PHASE_MODES}")


def _house_pv(net: pp.pandapowerNet) -> np.ndarray:
    """Installed kWp per home: the n-th PV system on a bus goes to the n-th home on that bus."""
    homes_at: dict[int, list[int]] = {}
    for h, bus in enumerate(net.load.bus.to_numpy()):
        homes_at.setdefault(int(bus), []).append(h)
    kwp = np.zeros(len(net.load))
    for bus, sn in zip(net.sgen.bus.to_numpy(), net.sgen.sn_mva.to_numpy()):
        queue = homes_at.get(int(bus), [])
        if not queue:
            raise ValueError(f"PV system on bus {bus} has no home to belong to")
        kwp[queue.pop(0)] = sn * 1000.0
    return kwp


def _xy_metres(net: pp.pandapowerNet) -> np.ndarray | None:
    """SimBench stores lon/lat; convert to local metres for distance-based tie candidates."""
    try:
        lonlat = np.array([json.loads(g)["coordinates"] for g in net.bus.geo], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    lon0, lat0 = lonlat[:, 0].mean(), lonlat[:, 1].mean()
    return np.c_[(lonlat[:, 0] - lon0) * 111_320 * np.cos(np.radians(lat0)), (lonlat[:, 1] - lat0) * 110_540]


def from_pandapower(net: pp.pandapowerNet, phases: str | np.ndarray = "random", r0_ratio: float = 3.0,
                    x0_ratio: float = 3.0, seed: int = 42, name: str = "simbench_rural2_india") -> Network:
    """Convert a pandapower net. Zero-sequence impedance is r0_ratio * r1 and x0_ratio * x1.

    The zero-sequence ratios are an unsourced assumption for a 4-wire Indian LV line; they are exposed
    so the sensitivity can be reported (gate G5).
    """
    bus_ids = net.bus.index.to_numpy()
    pos = {int(b): i for i, b in enumerate(bus_ids)}
    length = net.line.length_km.to_numpy()
    r1 = net.line.r_ohm_per_km.to_numpy() * length
    x1 = net.line.x_ohm_per_km.to_numpy() * length
    t = net.trafo.iloc[0]
    sn_va = float(t.sn_mva) * 1e6
    trafo = TrafoSpec(
        from_node=pos[int(t.hv_bus)], to_node=pos[int(t.lv_bus)],
        u1_v=float(t.vn_hv_kv) * 1000, u2_v=float(t.vn_lv_kv) * 1000, sn_va=sn_va,
        uk=float(t.vk_percent) / 100, pk_w=float(t.vkr_percent) / 100 * sn_va,
        i0=float(t.i0_percent) / 100, p0_w=float(t.pfe_kw) * 1000,
        clock=int(round(float(t.shift_degree) / 30)) % 12,
        tap_min=int(t.tap_min), tap_max=int(t.tap_max), tap_nom=int(t.tap_neutral),
        tap_size_v=float(t.tap_step_percent) / 100 * float(t.vn_hv_kv) * 1000,
    )
    n_homes = len(net.load)
    phase = assign_phases(n_homes, phases, seed) if isinstance(phases, str) else np.asarray(phases, dtype=int)
    return Network(
        name=name,
        node_kv=net.bus.vn_kv.to_numpy(float),
        lv_nodes=np.flatnonzero(net.bus.vn_kv.to_numpy() < 1),
        line_from=np.array([pos[int(b)] for b in net.line.from_bus]),
        line_to=np.array([pos[int(b)] for b in net.line.to_bus]),
        line_r1_ohm=r1, line_x1_ohm=x1, line_r0_ohm=r1 * r0_ratio, line_x0_ohm=x1 * x0_ratio,
        line_c1_f=net.line.c_nf_per_km.to_numpy() * 1e-9 * length,
        line_i_n_a=net.line.max_i_ka.to_numpy() * 1000,
        line_length_m=length * 1000,
        trafo=trafo,
        source_node=pos[int(net.ext_grid.bus.iloc[0])],
        house_node=np.array([pos[int(b)] for b in net.load.bus]),
        house_phase=phase,
        house_kwp=_house_pv(net),
        node_xy=_xy_metres(net),
        provenance={"topology": "benchmark: SimBench 1-LV-rural2, Indian overhead-line impedance",
                    "zero_sequence": f"assumed r0 = {r0_ratio} r1, x0 = {x0_ratio} x1 (unsourced)"},
    )
