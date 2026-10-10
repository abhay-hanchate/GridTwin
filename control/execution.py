"""Physical execution of explicit control actions: battery power and per-phase-group curtailment, any topology.

The battery is three pseudo-homes at its node (engine.fixes.battery.with_battery), one per phase, carrying a third of
its power each, at **unity power factor**: the homes keep the scenario's power factor through a per-home array, so
battery charging does not silently absorb reactive power. Curtailment keeps a fraction of each home's available solar,
per phase group, through the solver's per-step export limit: a limit of keep x available - demand delivers exactly
keep x available. Scenarios are laid side by side along the time axis, so any number of scenarios and steps is one
batched power flow. No reactive battery rule runs here: the battery does exactly what it is told.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.fixes.battery import with_battery
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayResult, DayScenarioBatch, Network

N_GROUPS = 3                    # curtailment groups: the homes of phase A, B and C
BASE = "base"


@dataclass(frozen=True, eq=False)
class StepInputs:
    """Uncontrolled inputs for S scenarios and T quarter hours (observed or forecast)."""
    load_kw: np.ndarray         # (S, T, H)
    pv_per_kwp: np.ndarray      # (S, T)
    upstream_pu: np.ndarray     # (S, T)
    t: pd.DatetimeIndex         # (T,)
    ambient_c: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.pv_per_kwp.shape

    def take(self, steps) -> "StepInputs":
        amb = None if self.ambient_c is None else self.ambient_c[:, steps]
        return StepInputs(self.load_kw[:, steps], self.pv_per_kwp[:, steps], self.upstream_pu[:, steps], self.t[steps], amb)


class Executor:
    """Solves explicit actions on the declared street. Topologies are registered by id ("base" is the street as built)."""

    def __init__(self, network: Network, *, battery_node: int, battery_kw_max: float, tap_pos: int = 0,
                 load_pf: float = 0.95, asymmetric: bool = True):
        self.base, self.node, self.kw_max, self.tap_pos = network, int(battery_node), float(battery_kw_max), tap_pos
        self.home_pf, self.asymmetric = load_pf, asymmetric
        self._nets: dict[str, Network] = {}
        self._solvers: dict[str, DaySolver] = {}
        self.add_topology(BASE, network)

    def add_topology(self, topology_id: str, network: Network) -> None:
        if network.n_homes != self.base.n_homes:
            raise ValueError("a topology may change lines only, not homes")
        self._nets[topology_id] = network
        spec = BatterySpec(kw=self.kw_max, kwh=1.0, node=self.node)          # energy is tracked by the controller
        self._solvers[topology_id] = DaySolver(with_battery(network, spec), asymmetric=self.asymmetric)

    def network(self, topology_id: str = BASE) -> Network:
        return self._nets[topology_id]

    @property
    def topologies(self) -> list[str]:
        return list(self._nets)

    def load_pf(self) -> np.ndarray:
        """Power factor per pseudo-home column: the homes' own, then 1.0 for the battery's three phases."""
        return np.r_[np.full(self.base.n_homes, self.home_pf), np.ones(3)]

    def group_of_home(self) -> np.ndarray:
        return self.base.house_phase.astype(int)

    def solve(self, inputs: StepInputs, battery_kw: np.ndarray, keep: np.ndarray, topology_id: str = BASE) -> DayResult:
        """battery_kw (T,) or (S, T), positive = charging; keep (T, 3) or (S, T, 3) kept solar share per phase group."""
        s, t = inputs.shape
        h = self.base.n_homes
        bat = np.broadcast_to(np.asarray(battery_kw, float), (s, t))
        kp = np.broadcast_to(np.asarray(keep, float), (s, t, N_GROUPS))
        if np.any(np.abs(bat) > self.kw_max + 1e-9):
            raise ValueError(f"battery power {np.abs(bat).max():.2f} kW exceeds its rating {self.kw_max} kW")
        if np.any((kp < -1e-9) | (kp > 1 + 1e-9)):
            raise ValueError("kept solar share must be within 0 and 1")
        load = np.concatenate([inputs.load_kw, np.repeat((bat / 3)[:, :, None], 3, axis=2)], axis=2)    # (S, T, H+3)
        avail = inputs.pv_per_kwp[:, :, None] * self.base.house_kwp[None, None, :]                    # (S, T, H)
        delivered = avail * kp[:, :, self.group_of_home()]
        lim = np.concatenate([delivered - inputs.load_kw, -np.repeat((bat / 3)[:, :, None], 3, axis=2)], axis=2)
        flat = lambda a: a.reshape(1, s * t, *a.shape[2:])  # noqa: E731
        times = pd.DatetimeIndex(np.tile(np.asarray(inputs.t), s))
        amb = None if inputs.ambient_c is None else flat(inputs.ambient_c)
        batch = DayScenarioBatch(times, flat(load), flat(inputs.pv_per_kwp), flat(inputs.upstream_pu), self.load_pf(),
                                 ("flat",), amb)
        controls = Controls(tap_pos=self.tap_pos, export_limit_kw=lim.reshape(s * t, h + 3))
        res = self._solvers[topology_id].solve(batch, controls)
        back = lambda a: a.reshape(s, t, *a.shape[2:])  # noqa: E731
        return DayResult(
            t=inputs.t, u_pu=back(res.u_pu), line_loading_pct=back(res.line_loading_pct),
            trafo_loading_pct=back(res.trafo_loading_pct), trafo_p_kw=back(res.trafo_p_kw), losses_kw=back(res.losses_kw),
            q_loss_kvar=back(res.q_loss_kvar), pv_kw=back(res.pv_kw), pv_avail_kw=back(res.pv_avail_kw),
            inverter_kvar=back(res.inverter_kvar), battery_kw=bat.copy(), neutral_a=back(res.neutral_a),
            vuf_pct=back(res.vuf_pct), converged=back(res.converged), passes=res.passes)
