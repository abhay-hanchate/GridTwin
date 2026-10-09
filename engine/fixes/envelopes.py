"""D4: day-ahead per-house export limits (operating envelopes) by per-step bisection.

For every step independently, find the largest per-home export cap (kW) at which that step is safe.
Steps are independent without a battery, so all 96 bisections run together as one batch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import evaluate


@dataclass
class Envelope:
    limit_kw: np.ndarray        # (T, H) maximum net export per home per step
    infeasible: np.ndarray      # (T,) steps unsafe even at zero export
    curtailed_kwh: float
    iterations: int


def compute_envelope(solver: DaySolver, scn: DayScenarioBatch, rule: VoltageRule, base: Controls = Controls(),
                     weights: np.ndarray | None = None, iterations: int = 14) -> Envelope:
    """`weights` (H,) in (0, 1] scale each home's share of the cap (equal shares by default)."""
    if scn.shape[0] != 1:
        raise ValueError("envelopes are computed for one scenario at a time")
    t = scn.shape[1]
    n_h = solver.network.n_homes
    w = np.ones(n_h) if weights is None else np.asarray(weights, dtype=float)
    cap_max = float(solver.network.house_kwp.max() or 1.0)
    lo, hi = np.zeros(t), np.full(t, cap_max)

    def unsafe_at(c: np.ndarray) -> np.ndarray:
        limit = c[:, None] * w[None, :]
        res = solver.solve(scn, _with_limit(base, limit))
        return evaluate(res, rule).unsafe[0]

    zero_unsafe = unsafe_at(np.zeros(t))
    if not unsafe_at(hi).any():                               # nothing to limit anywhere
        lo = hi.copy()
    else:
        for _ in range(iterations):
            mid = (lo + hi) / 2
            bad = unsafe_at(mid)
            hi = np.where(bad, mid, hi)
            lo = np.where(bad, lo, mid)
    cap = np.where(zero_unsafe, 0.0, lo)
    limit = cap[:, None] * w[None, :]
    res = solver.solve(scn, _with_limit(base, limit))
    curtailed = float((res.pv_avail_kw - res.pv_kw).sum() * 0.25)
    return Envelope(limit_kw=limit, infeasible=zero_unsafe, curtailed_kwh=curtailed, iterations=iterations)


def _with_limit(base: Controls, limit: np.ndarray) -> Controls:
    from dataclasses import replace
    return replace(base, export_limit_kw=limit)
