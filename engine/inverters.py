"""IEEE 1547-2018 smart-inverter characteristics (pure functions), used by the v2 batch engine (engine/solver.py).

Conventions (IEEE 1547-2018):
- Volt/VAR gives reactive power as a fraction of the inverter's nameplate apparent power, positive when the
  inverter injects and negative when it absorbs.
- Volt/Watt gives a LIMIT on active power as a fraction of rated active power (P1 = Prated at 1.06 pu,
  P2 = 0.2 Prated at 1.10 pu). Output is min(available, limit), so a panel that already produces less than the
  limit is not curtailed. It is not a percentage of the available power.

The engine solves the response as a damped fixed point over whole batches: every inverter responds to the voltage
at its own bus and its set-points move a fraction of the way toward the curve.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
