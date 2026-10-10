"""Guard bands from held-out calibration states, and the screening decision they feed.

For each extreme, the one-sided split-conformal quantile of the residual in the dangerous direction (the model
under-states a high voltage or a loading, or over-states a low voltage) and, separately, in the optimistic direction.
Each is taken at level 1 - alpha/4 (Bonferroni over the four extremes) with the finite-sample rank ceil((n+1)(1-a)),
and never below zero. Validity assumes the calibration and screened states are exchangeable; states picked by an
optimiser or outside the trained box can break that, which is why the solver still verifies every choice.
"""
from __future__ import annotations

import math

import numpy as np

ALPHA = 0.005
FAILURE_THRESHOLD = 0.01
# Sign that turns (true - predicted) into "the model was too optimistic" for each extreme.
DANGER_SIGN = np.array([1.0, -1.0, 1.0, 1.0])


def conformal_quantile(residuals: np.ndarray, level: float) -> float:
    r = np.sort(np.asarray(residuals, float)[np.isfinite(residuals)])
    n = len(r)
    if n == 0:
        return math.inf
    k = math.ceil((n + 1) * level)
    return math.inf if k > n else max(float(r[k - 1]), 0.0)


def fit_guard(pred: np.ndarray, true: np.ndarray, alpha: float = ALPHA) -> dict:
    """pred and true (B, 4) extremes of converged calibration states. Returns per-extreme margins."""
    level = 1 - alpha / 4
    resid = (true - pred) * DANGER_SIGN
    return {"danger": [conformal_quantile(resid[:, k], level) for k in range(4)],
            "optimistic": [conformal_quantile(-resid[:, k], level) for k in range(4)],
            "alpha": alpha, "level": level, "n": int(len(pred))}


def bounds(pred: np.ndarray, guard: dict) -> tuple[np.ndarray, np.ndarray]:
    """(guarded, optimistic): the extremes moved toward danger by the danger margin, and away by the optimistic one."""
    d, o = np.asarray(guard["danger"]), np.asarray(guard["optimistic"])
    return pred + DANGER_SIGN * d, pred - DANGER_SIGN * o


def crosses(ext: np.ndarray, vmin_pu: float, vmax_pu: float) -> np.ndarray:
    """Whether extremes (B, 4) break the band or 100% loading, with the engine's strict comparisons."""
    with np.errstate(invalid="ignore"):
        return (ext[:, 0] > vmax_pu) | (ext[:, 1] < vmin_pu) | (ext[:, 2] > 100) | (ext[:, 3] > 100)


def decide(pred: np.ndarray, guard: dict, vmin_pu: float, vmax_pu: float, p_fail: np.ndarray | None = None,
           failure_threshold: float = FAILURE_THRESHOLD) -> dict:
    guarded, optimistic = bounds(pred, guard)
    risky = crosses(guarded, vmin_pu, vmax_pu) | ~np.isfinite(guarded).all(axis=1)
    if p_fail is not None:
        risky |= p_fail > failure_threshold
    return {"guarded": guarded, "optimistic": optimistic, "risky": risky,
            "clearly_unsafe": crosses(optimistic, vmin_pu, vmax_pu), "point_unsafe": crosses(pred, vmin_pu, vmax_pu)}
