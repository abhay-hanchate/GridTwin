"""D1: turn sampled scenarios into a probability of unsafe voltage or overload."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import STEP_H, evaluate

WINDOWS_STEPS = {"15 min": 1, "1 h": 4, "3 h": 12, "24 h": 96}


def longest_run(flags: np.ndarray) -> np.ndarray:
    """Longest run of consecutive True per row of an (S, T) boolean array."""
    best = np.zeros(flags.shape[0], dtype=int)
    cur = np.zeros(flags.shape[0], dtype=int)
    for t in range(flags.shape[1]):
        cur = np.where(flags[:, t], cur + 1, 0)
        best = np.maximum(best, cur)
    return best


@dataclass
class RiskResult:
    t: pd.DatetimeIndex
    p_unsafe: np.ndarray                 # (T,) share of scenarios unsafe at each step
    expected_unsafe_hours: float
    unsafe_hours_p10: float
    unsafe_hours_p90: float
    peak_voltage_v: dict                 # P10 / P50 / P90 of the per-scenario peak phase voltage
    level: str                           # "ok", "watch" or "act"
    first_watch: str | None
    first_act: str | None
    shares: dict                         # probability that a scenario has any violation of each kind
    window_risk: dict                    # probability of an unsafe spell at least this long
    n_scenarios: int
    rule_id: str
    extra: dict = field(default_factory=dict)


def assess_risk(solver: DaySolver, scn: DayScenarioBatch, controls: Controls, rule: VoltageRule, *,
                watch: float = 0.20, act: float = 0.50) -> RiskResult:
    res = solver.solve(scn, controls)
    viol = evaluate(res, rule)
    n = scn.shape[0]
    p = viol.unsafe.mean(axis=0)
    hours = viol.unsafe.sum(axis=1) * STEP_H
    peak_v = np.nanmax(np.where(res.converged[:, :, None, None], res.u_pu, np.nan), axis=(1, 2, 3)) * 230.0
    runs = longest_run(viol.unsafe)
    stamp = lambda i: scn.t[int(i)].strftime("%H:%M")  # noqa: E731
    watch_idx, act_idx = np.flatnonzero(p >= watch), np.flatnonzero(p >= act)
    return RiskResult(
        t=scn.t, p_unsafe=p, expected_unsafe_hours=float(hours.mean()),
        unsafe_hours_p10=float(np.quantile(hours, 0.1)), unsafe_hours_p90=float(np.quantile(hours, 0.9)),
        peak_voltage_v={f"p{q}": float(np.nanquantile(peak_v, q / 100)) for q in (10, 50, 90)},
        level="act" if len(act_idx) else "watch" if len(watch_idx) else "ok",
        first_watch=stamp(watch_idx[0]) if len(watch_idx) else None,
        first_act=stamp(act_idx[0]) if len(act_idx) else None,
        shares={k: float(getattr(viol, k).any(axis=1).mean()) for k in ("over", "under", "line", "trafo", "solver")},
        window_risk={name: float((runs >= steps).mean()) for name, steps in WINDOWS_STEPS.items()},
        n_scenarios=n, rule_id=rule.id,
        extra={"passes": res.passes},
    )
