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


def fit_guard(pred: np.ndarray, true: np.ndarray, alpha: float = ALPHA, bins: int | None = None) -> dict:
    """pred and true (B, 4) extremes of converged calibration states. Returns per-extreme margins.

    With `bins` (Mondrian, round 2), each extreme's calibration states are cut into `bins` groups at the quantiles of
    the predicted value, and each group gets its own margin; `edges` holds the inner cut points per extreme."""
    level = 1 - alpha / 4
    resid = (true - pred) * DANGER_SIGN
    if not bins:
        return {"danger": [conformal_quantile(resid[:, k], level) for k in range(4)],
                "optimistic": [conformal_quantile(-resid[:, k], level) for k in range(4)],
                "alpha": alpha, "level": level, "n": int(len(pred))}
    edges, danger, optimistic, counts = [], [], [], []
    for k in range(4):
        inner = np.quantile(pred[:, k], np.linspace(0, 1, bins + 1)[1:-1])
        which = np.searchsorted(inner, pred[:, k], side="right")
        edges.append(inner.tolist())
        danger.append([conformal_quantile(resid[which == b, k], level) for b in range(bins)])
        optimistic.append([conformal_quantile(-resid[which == b, k], level) for b in range(bins)])
        counts.append([int((which == b).sum()) for b in range(bins)])
    return {"danger": danger, "optimistic": optimistic, "edges": edges, "bin_counts": counts, "alpha": alpha,
            "level": level, "n": int(len(pred)), "method": "mondrian by predicted value"}


def margins(pred: np.ndarray, guard: dict, side: str) -> np.ndarray:
    """(B, 4) margin per state and extreme: one value per extreme, or the value of the state's predicted-value bin."""
    if "edges" not in guard:
        return np.broadcast_to(np.asarray(guard[side], float), pred.shape)
    out = np.empty(pred.shape)
    for k in range(4):
        table = np.asarray(guard[side][k], float)
        idx = np.searchsorted(np.asarray(guard["edges"][k]), np.nan_to_num(pred[:, k], nan=0.0), side="right")
        out[:, k] = table[idx]
    return out


def bounds(pred: np.ndarray, guard: dict) -> tuple[np.ndarray, np.ndarray]:
    """(guarded, optimistic): the extremes moved toward danger by the danger margin, and away by the optimistic one."""
    return pred + DANGER_SIGN * margins(pred, guard, "danger"), pred - DANGER_SIGN * margins(pred, guard, "optimistic")


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


def margin_at(guard: dict, k: int, value: float, side: str = "danger") -> float:
    """The margin applied to extreme `k` for a state predicted exactly at `value` (e.g. at a limit), for reports."""
    return float(margins(np.array([[value] * 4], float), guard, side)[0, k])


def limit_margins(guard: dict) -> dict:
    """Danger margins where decisions are made: at each rule's voltage limits (volts) and at 100% loading (points)."""
    from engine.rules import get_rule
    out = {}
    for rid in ("up_2005", "pm10"):
        r = get_rule(rid)
        out[rid] = {"v_max_v": round(margin_at(guard, 0, r.vmax_pu) * r.nominal_v, 3),
                    "v_min_v": round(margin_at(guard, 1, r.vmin_pu) * r.nominal_v, 3)}
    out["line_pts"], out["trafo_pts"] = round(margin_at(guard, 2, 100.0), 3), round(margin_at(guard, 3, 100.0), 3)
    return out
