"""The verification contract: storage and equipment rules before an action runs, every declared physical limit after.

A missing or non-finite solver output is a failure, never a zero violation. Voltage unbalance is checked only when a
limit is declared (it is not an enforced limit of the benchmark configuration otherwise).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from control.types import Action, BatteryModel, ControlState, SwitchPolicy, operations_for
from engine.rules import VoltageRule
from engine.types import DayResult

NOMINAL_V = 230.0


def action_errors(state: ControlState, action: Action, battery: BatteryModel, policy: SwitchPolicy, step: int) -> list[str]:
    """Reasons an action may not run (empty when permitted)."""
    errs = []
    p = action.battery_kw
    if not np.isfinite(p) or abs(p) > battery.kw + 1e-9:
        errs.append(f"battery power {p:.2f} kW outside the {battery.kw} kW rating")
    elif p > 0 and battery.next_energy(state.energy_kwh, p) > battery.e_max + 1e-6:
        errs.append(f"charging {p:.2f} kW would take the energy above {battery.e_max:.2f} kWh")
    elif p < 0 and battery.next_energy(state.energy_kwh, p) < battery.e_min - 1e-6:
        errs.append(f"discharging {-p:.2f} kW would take the energy below {battery.e_min:.2f} kWh")
    if any((not np.isfinite(k)) or k < -1e-9 or k > 1 + 1e-9 for k in action.keep):
        errs.append("kept solar share must be within 0 and 1")
    if action.topology_id != state.topology_id:
        if action.topology_id != "base" and action.topology_id not in policy.allowed:
            errs.append(f"switch {action.topology_id} is not permitted")
        ops = operations_for(state.topology_id, action.topology_id)
        if state.operations_used + ops > policy.max_operations:
            errs.append(f"switching needs {ops} operations; the daily budget has "
                        f"{policy.max_operations - state.operations_used} left")
        if state.last_switch_step is not None and step - state.last_switch_step < policy.dwell_steps:
            errs.append(f"minimum dwell of {policy.dwell_steps} quarter hours since the last switching not reached")
    return errs


@dataclass
class Check:
    safe: np.ndarray            # (S, T) every declared limit met and the solve converged
    severity: np.ndarray        # (S, T) worst exceedance in volt-equivalents (loading: 1 V per 10 %); inf if no solve
    v_max_v: np.ndarray         # (S, T)
    v_min_v: np.ndarray
    line_max_pct: np.ndarray
    trafo_pct: np.ndarray
    vuf_pct: np.ndarray
    margin_v: np.ndarray        # (S, T) distance to the nearer voltage limit (negative when outside)
    reasons: list[list[str]]    # [s][t] what failed


def physical_check(res: DayResult, rule: VoltageRule, *, vuf_limit: float | None = None) -> Check:
    with np.errstate(invalid="ignore", all="ignore"):
        u = res.u_pu * NOMINAL_V
        finite = np.isfinite(u).all(axis=(2, 3)) & np.isfinite(res.line_loading_pct).all(axis=2) & np.isfinite(res.trafo_loading_pct)
        ok = res.converged & finite
        vmax = np.nanmax(u, axis=(2, 3))
        vmin = np.nanmin(u, axis=(2, 3))
        line = np.nanmax(res.line_loading_pct, axis=2)
        trafo = res.trafo_loading_pct
        over = np.maximum(vmax - rule.vmax_v, 0)
        under = np.maximum(rule.vmin_v - vmin, 0)
        line_x = np.maximum(line - 100, 0) / 10
        trafo_x = np.maximum(trafo - 100, 0) / 10
        vuf_x = np.maximum(res.vuf_pct - vuf_limit, 0) * 10 if vuf_limit is not None else np.zeros_like(vmax)
        sev = np.maximum.reduce([over, under, line_x, trafo_x, vuf_x])
        sev = np.where(ok, sev, np.inf)
        safe = ok & (sev <= 0)
        margin = np.minimum(rule.vmax_v - vmax, vmin - rule.vmin_v)
    reasons = []
    for s in range(safe.shape[0]):
        row = []
        for t in range(safe.shape[1]):
            r = []
            if not ok[s, t]:
                r.append("solver did not converge or gave non-finite outputs")
            else:
                if over[s, t] > 0:
                    r.append(f"over-voltage {vmax[s, t]:.1f} V > {rule.vmax_v:.1f} V")
                if under[s, t] > 0:
                    r.append(f"under-voltage {vmin[s, t]:.1f} V < {rule.vmin_v:.1f} V")
                if line_x[s, t] > 0:
                    r.append(f"line loading {line[s, t]:.0f}% > 100%")
                if trafo_x[s, t] > 0:
                    r.append(f"transformer loading {trafo[s, t]:.0f}% > 100%")
                if vuf_x[s, t] > 0:
                    r.append(f"voltage unbalance {res.vuf_pct[s, t]:.2f}% > {vuf_limit}%")
            row.append(r)
        reasons.append(row)
    return Check(safe=safe, severity=sev, v_max_v=vmax, v_min_v=vmin, line_max_pct=line, trafo_pct=trafo,
                 vuf_pct=res.vuf_pct, margin_v=margin, reasons=reasons)
