"""IEEE 1547-2018 smart-inverter characteristics (pure functions) and a pandapower controller.

Sign convention: Q fractions are positive when the inverter injects reactive power and negative when it
absorbs, as a fraction of rated apparent power. pandapower sgen q_mvar uses the same sign.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandapower as pp


@dataclass(frozen=True)
class VoltVarCurve:
    v_pu: tuple = (0.92, 0.98, 1.02, 1.08)
    q_frac: tuple = (0.44, 0.0, 0.0, -0.44)
    name: str = "IEEE 1547-2018 Category B"

    def q_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.q_frac)


@dataclass(frozen=True)
class VoltWattCurve:
    v_pu: tuple = (1.06, 1.10)
    p_frac: tuple = (1.0, 0.2)
    name: str = "IEEE 1547-2018 Volt-Watt (confirm against the BIS annexure)"

    def p_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.p_frac)


# Reactive limits of +-100% of the *available* capacity sqrt(S^2 - P^2); the controller clips to it.
GUJARAT_VOLT_VAR = VoltVarCurve(v_pu=(0.94, 0.99, 1.01, 1.06), q_frac=(1.0, 0.0, 0.0, -1.0),
                                name="Preset from the Gujarat-authored 2026 paper")


class InverterControl:
    """Damped fixed-point solve so every inverter responds to the voltage at its own bus."""

    def __init__(self, volt_var: VoltVarCurve | None = None, volt_watt: VoltWattCurve | None = None,
                 damping: float = 0.5, tol_mw: float = 1e-6, max_iter: int = 40, s_factor: float = 1.0):
        self.volt_var, self.volt_watt = volt_var, volt_watt
        self.damping, self.tol_mw, self.max_iter, self.s_factor = damping, tol_mw, max_iter, s_factor
        self.iterations: list[int] = []

    def solve(self, net: pp.pandapowerNet, step: int) -> None:
        sn = net.sgen.sn_mva.to_numpy() * self.s_factor
        p_avail = net.sgen.p_mw.to_numpy().copy()
        buses = net.sgen.bus.to_numpy()
        p, q = p_avail.copy(), np.zeros_like(p_avail)
        for k in range(self.max_iter):
            net.sgen["p_mw"] = p
            net.sgen["q_mvar"] = q
            pp.runpp(net, numba=True, init="results" if (step or k) else "auto")
            v = net.res_bus.loc[buses, "vm_pu"].to_numpy()
            p_t = p_avail * (self.volt_watt.p_fraction(v) if self.volt_watt else 1.0)
            cap = np.sqrt(np.maximum(sn ** 2 - p_t ** 2, 0.0))
            q_t = np.clip(sn * self.volt_var.q_fraction(v), -cap, cap) if self.volt_var else np.zeros_like(p)
            dp, dq = p_t - p, q_t - q
            if max(np.abs(dp).max(initial=0.0), np.abs(dq).max(initial=0.0)) < self.tol_mw:
                self.iterations.append(k + 1)
                return
            p, q = p + self.damping * dp, q + self.damping * dq
        raise pp.LoadflowNotConverged("inverter control did not settle")
