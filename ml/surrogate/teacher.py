"""The teacher: solve arrays of single-quarter-hour operating states with the real solver.

Each state is one street at one quarter hour, on one of its layouts (as built or a permitted switched one). The battery
is three pseudo-homes at its node carrying a third of its power each at unity power factor (as control/execution.py);
homes keep power factor 0.95. Delivered solar is set through the per-step export limit with one kW of "sun" per
installed kWp, so a home delivers exactly `pv_kw` (before any Volt/Watt cut) and its inverter is rated at its kWp.
States that share layout, battery node, tap, inverter mode and solar sizes are one batched power flow.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, fields

import numpy as np
import pandas as pd

from engine.fixes.battery import with_battery
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network
from ml.surrogate.schema import LOAD_PF, MODES, topologies

_VV, _VW = VoltVarCurve(), VoltWattCurve()
MODE_CONTROLS = {"fixed_pf": {}, "volt_var": {"volt_var": _VV}, "volt_watt": {"volt_watt": _VW},
                 "volt_var_watt": {"volt_var": _VV, "volt_watt": _VW}}


@dataclass(frozen=True, eq=False)
class StateArrays:
    load_kw: np.ndarray        # (B, H)
    pv_kw: np.ndarray          # (B, H) delivered solar before any Volt/Watt cut
    pv_kwp: np.ndarray         # (B, H) installed solar (inverter rating)
    upstream_pu: np.ndarray    # (B,)
    battery_kw: np.ndarray     # (B,) + charging
    tap_pos: np.ndarray        # (B,) int
    mode: np.ndarray           # (B,) index into MODES
    battery_node: np.ndarray   # (B,) node of the battery, -1 when there is none
    topology: np.ndarray       # (B,) index into schema.topologies (0 = as built)

    def __len__(self) -> int:
        return len(self.upstream_pu)

    def take(self, idx) -> "StateArrays":
        return StateArrays(**{f.name: getattr(self, f.name)[idx] for f in fields(self)})

    @classmethod
    def concat(cls, parts: list["StateArrays"]) -> "StateArrays":
        return cls(**{f.name: np.concatenate([getattr(p, f.name) for p in parts]) for f in fields(cls)})


LABEL_KEYS = ("u_pu", "line_loading_pct", "trafo_loading_pct", "converged", "passes", "vuf_pct", "neutral_a", "trafo_p_kw")


@dataclass
class Labels:
    u_pu: np.ndarray               # (B, Nlv, 3)
    line_loading_pct: np.ndarray   # (B, L)
    trafo_loading_pct: np.ndarray  # (B,)
    converged: np.ndarray          # (B,) bool
    passes: np.ndarray             # (B,) inverter-control passes of the batch the state was in
    vuf_pct: np.ndarray            # (B,) worst voltage unbalance factor on the street
    neutral_a: np.ndarray          # (B,) neutral current at the transformer
    trafo_p_kw: np.ndarray         # (B,) into the transformer's HV side; negative = reverse flow

    def take(self, idx) -> "Labels":
        return Labels(*(getattr(self, k)[idx] for k in LABEL_KEYS))

    @classmethod
    def concat(cls, parts: list["Labels"]) -> "Labels":
        return cls(*(np.concatenate([getattr(p, k) for p in parts]) for k in LABEL_KEYS))

    def extremes(self) -> np.ndarray:
        """(B, 4): highest and lowest voltage, worst line and transformer loading (NaN where the solve failed)."""
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.stack([np.nanmax(self.u_pu, axis=(1, 2)), np.nanmin(self.u_pu, axis=(1, 2)),
                             np.nanmax(self.line_loading_pct, axis=1), self.trafo_loading_pct], axis=1)

    def extras(self) -> np.ndarray:
        """(B, 3): voltage unbalance (%), neutral current (A), transformer power (kW)."""
        return np.stack([self.vuf_pct, self.neutral_a, self.trafo_p_kw], axis=1)


def _solve_group(net: Network, kwp: np.ndarray, s: StateArrays, tap: int, mode: str, node: int) -> dict:
    b, h = len(s), net.n_homes
    grid = with_battery(net.with_pv(kwp), BatterySpec(kw=1.0, kwh=1.0, node=node))
    bat = np.repeat((s.battery_kw / 3)[:, None], 3, axis=1)
    load = np.concatenate([s.load_kw, bat], axis=1)
    # p_cap = min(available, load + limit): with available = kWp this delivers pv_kw for homes and zero for the battery.
    lim = np.concatenate([s.pv_kw - s.load_kw, -bat], axis=1)
    pf = np.r_[np.full(h, LOAD_PF), np.ones(3)]
    batch = DayScenarioBatch(pd.date_range("2025-01-01", periods=b, freq="15min"), load[None], np.ones((1, b)),
                             s.upstream_pu[None].astype(float), pf, ("states",))
    res = DaySolver(grid).solve(batch, Controls(tap_pos=int(tap), export_limit_kw=lim, **MODE_CONTROLS[mode]))
    return {"u_pu": res.u_pu[0], "line_loading_pct": res.line_loading_pct[0], "trafo_loading_pct": res.trafo_loading_pct[0],
            "converged": res.converged[0], "passes": np.full(b, res.passes), "vuf_pct": res.vuf_pct[0],
            "neutral_a": res.neutral_a[0], "trafo_p_kw": res.trafo_p_kw[0]}


def solve_states(net: Network, states: StateArrays, *, layouts: list[Network] | None = None, max_batch: int = 4096) -> Labels:
    """`net` is the street as built; each state's layout is `layouts[topology]` (default: schema.topologies(net)).
    A state without a battery puts the idle pseudo-homes at the street's first home node (zero power: no effect)."""
    b = len(states)
    if np.any(states.pv_kw > states.pv_kwp + 1e-9):
        raise ValueError("delivered solar exceeds the installed kWp")
    layouts = layouts if layouts is not None else topologies(net)
    out = {"u_pu": np.full((b, len(net.lv_nodes), 3), np.nan), "line_loading_pct": np.full((b, net.n_lines), np.nan),
           "trafo_loading_pct": np.full(b, np.nan), "converged": np.zeros(b, bool), "passes": np.zeros(b, int),
           "vuf_pct": np.full(b, np.nan), "neutral_a": np.full(b, np.nan), "trafo_p_kw": np.full(b, np.nan)}
    node = np.where(states.battery_node >= 0, states.battery_node, int(net.house_node[0]))
    kwp_rows, kwp_id = np.unique(states.pv_kwp, axis=0, return_inverse=True)
    keys = np.stack([kwp_id.ravel(), states.tap_pos.astype(int), states.mode.astype(int), node.astype(int),
                     states.topology.astype(int)], axis=1)
    for key in np.unique(keys, axis=0):
        idx = np.flatnonzero((keys == key).all(axis=1))
        for start in range(0, len(idx), max_batch):
            part = idx[start:start + max_batch]
            got = _solve_group(layouts[key[4]], kwp_rows[key[0]], states.take(part), key[1], MODES[key[2]], int(key[3]))
            for k, v in got.items():
                out[k][part] = v
    return Labels(**out)
