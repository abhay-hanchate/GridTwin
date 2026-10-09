"""IEEE 1547-2018 smart-inverter characteristics (pure functions) and a pandapower controller.

Conventions (IEEE 1547-2018 and pandapower sgen):
- Volt/VAR gives reactive power as a fraction of the inverter's nameplate apparent power, positive when the
  inverter injects and negative when it absorbs (pandapower sgen q_mvar uses the same sign).
- Volt/Watt gives a LIMIT on active power as a fraction of rated active power (P1 = Prated at 1.06 pu,
  P2 = 0.2 Prated at 1.10 pu). Output is min(available, limit), so a panel that already produces less than the
  limit is not curtailed. It is not a percentage of the available power.

The solve is a damped fixed point: every inverter responds to the voltage at its own bus, its set-points move a
fraction of the way toward the curve, and the power flow is re-run until no set-point moves more than `tol_mw`.
This is the same update as pandapower's DERController (damping_coef) and OpenDSS InvControl (DeltaQ_factor);
pandapower has no Volt/Watt model, so the loop is written here and the curve functions are reused by the v2
batch engine.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandapower as pp


@dataclass(frozen=True)
class VoltVarCurve:
    """IEEE 1547-2018 Category B default (VRef = 1.0 pu): Q = +44% / -44% of nameplate VA at 0.92 / 1.08 pu."""
    v_pu: tuple = (0.92, 0.98, 1.02, 1.08)
    q_frac: tuple = (0.44, 0.0, 0.0, -0.44)
    name: str = "IEEE 1547-2018 Category B default"

    def q_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.q_frac)


@dataclass(frozen=True)
class VoltWattCurve:
    """IEEE 1547-2018 default: no limit up to 1.06 pu, falling to 20% of rated active power at 1.10 pu."""
    v_pu: tuple = (1.06, 1.10)
    p_frac: tuple = (1.0, 0.2)
    name: str = "IEEE 1547-2018 Volt-Watt default"

    def p_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.p_frac)


class InverterControl:
    """Volt/VAR and/or Volt/Watt for every sgen of a pandapower net, solved by damped fixed-point iteration."""

    def __init__(self, volt_var: VoltVarCurve | None = None, volt_watt: VoltWattCurve | None = None,
                 damping: float = 0.5, tol_mw: float = 1e-6, max_iter: int = 60, s_factor: float = 1.0):
        self.volt_var, self.volt_watt = volt_var, volt_watt
        self.damping, self.tol_mw, self.max_iter, self.s_factor = damping, tol_mw, max_iter, s_factor
        self.iterations: list[int] = []

    def solve(self, net: pp.pandapowerNet, step: int) -> None:
        sn = net.sgen.sn_mva.to_numpy() * self.s_factor             # nameplate apparent power
        p_avail = net.sgen.p_mw.to_numpy().copy()
        buses = net.sgen.bus.to_numpy()
        p, q = p_avail.copy(), np.zeros_like(p_avail)
        for k in range(self.max_iter):
            net.sgen["p_mw"] = p
            net.sgen["q_mvar"] = q
            pp.runpp(net, numba=True, init="results" if (step or k) else "auto")
            v = net.res_bus.loc[buses, "vm_pu"].to_numpy()
            p_t = np.minimum(p_avail, sn * self.volt_watt.p_fraction(v)) if self.volt_watt else p_avail
            cap = np.sqrt(np.maximum(sn ** 2 - p_t ** 2, 0.0))      # watt priority: Q uses what P leaves
            q_t = np.clip(sn * self.volt_var.q_fraction(v), -cap, cap) if self.volt_var else np.zeros_like(p)
            dp, dq = p_t - p, q_t - q
            if max(np.abs(dp).max(initial=0.0), np.abs(dq).max(initial=0.0)) < self.tol_mw:
                self.iterations.append(k + 1)
                return
            p, q = p + self.damping * dp, q + self.damping * dq
        raise pp.LoadflowNotConverged(f"inverter control did not settle in {self.max_iter} iterations")
