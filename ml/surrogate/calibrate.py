"""Guard bands from held-out calibration states, and the screening decision they feed.

For each output, the one-sided split-conformal quantile of the residual in the dangerous direction (the model
under-states a high voltage, a loading, the unbalance or the neutral current, over-states a low voltage, or over-states
the transformer power so that reverse flow would be missed) and, separately, in the optimistic direction. Level
1 - alpha/4 (Bonferroni over the four extremes), finite-sample rank ceil((n+1)(1-a)), never below zero.

Margins can depend on the predicted value (Mondrian): round 2 cut each output at quantiles of the prediction; round 4
cuts the four extremes at their decision limits (+-1.5% for voltage, +-10 points for loading) and merges neighbouring
bins until each holds `min_count` calibration states. Validity assumes the calibration and screened states are
exchangeable within a bin; states picked by an optimiser or outside the trained range can break that, which is why the
solver still verifies every choice.
"""
from __future__ import annotations

import math

import numpy as np

ALPHA = 0.005
FAILURE_THRESHOLD = 0.01
QUANTILE_BINS = 8
MIN_COUNT = 1000
# Sign that turns (true - predicted) into "the model was too optimistic", per output (EXTREMES + EXTRAS).
DANGER_SIGN = np.array([1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0])
VOLTAGE_LIMITS, VOLTAGE_HALF_WIDTH = (0.90, 0.94, 1.06, 1.10), 0.015
LOADING_LIMIT, LOADING_HALF_WIDTH = 100.0, 10.0


def conformal_quantile(residuals: np.ndarray, level: float) -> float:
    r = np.sort(np.asarray(residuals, float)[np.isfinite(residuals)])
    n = len(r)
    if n == 0:
        return math.inf
    k = math.ceil((n + 1) * level)
    return math.inf if k > n else max(float(r[k - 1]), 0.0)


def limit_edges() -> list:
    """Round 4 cut points: each decision limit +- a half width, for the four extremes; None = quantile bins."""
    v = sorted({round(x, 6) for lim in VOLTAGE_LIMITS for x in (lim - VOLTAGE_HALF_WIDTH, lim + VOLTAGE_HALF_WIDTH)})
    load = [LOADING_LIMIT - LOADING_HALF_WIDTH, LOADING_LIMIT + LOADING_HALF_WIDTH]
    return [v, v, load, load, None, None, None]


def _merge(inner: list[float], values: np.ndarray, min_count: int) -> list[float]:
    """Remove cut points, smallest bin first (merged with its smaller neighbour), until every bin is big enough."""
    inner = list(inner)
    while inner:
        counts = np.bincount(np.searchsorted(inner, values, side="right"), minlength=len(inner) + 1)
        i = int(counts.argmin())
        if counts[i] >= min_count:
            break
        if i == 0:
            inner.pop(0)
        elif i == len(counts) - 1:
            inner.pop(-1)
        else:
            inner.pop(i - 1 if counts[i - 1] <= counts[i + 1] else i)
    return inner


def fit_guard(pred: np.ndarray, true: np.ndarray, alpha: float = ALPHA, bins: int | None = None,
              edges: list | None = None, min_count: int = MIN_COUNT) -> dict:
    """pred and true (B, K) outputs of converged calibration states. Returns per-output margins: one value each, or
    (with `bins` or `edges`) one per predicted-value bin, with `edges` holding the inner cut points per output."""
    level = 1 - alpha / 4
    k_out = pred.shape[1]
    resid = (true - pred) * DANGER_SIGN[:k_out]
    if not bins and edges is None:
        return {"danger": [conformal_quantile(resid[:, k], level) for k in range(k_out)],
                "optimistic": [conformal_quantile(-resid[:, k], level) for k in range(k_out)],
                "alpha": alpha, "level": level, "n": int(len(pred))}
    out = {"danger": [], "optimistic": [], "edges": [], "bin_counts": [], "alpha": alpha, "level": level,
           "n": int(len(pred)), "method": "mondrian by predicted value" + (", centred on the limits" if edges else "")}
    for k in range(k_out):
        cut = edges[k] if edges is not None else None
        if cut is None:
            cut = np.quantile(pred[:, k], np.linspace(0, 1, (bins or QUANTILE_BINS) + 1)[1:-1]).tolist()
        elif edges is not None:
            cut = _merge(sorted(cut), pred[:, k], min_count)
        which = np.searchsorted(cut, pred[:, k], side="right")
        nb = len(cut) + 1
        out["edges"].append(list(cut))
        out["danger"].append([conformal_quantile(resid[which == b, k], level) for b in range(nb)])
        out["optimistic"].append([conformal_quantile(-resid[which == b, k], level) for b in range(nb)])
        out["bin_counts"].append([int((which == b).sum()) for b in range(nb)])
    return out


def margins(pred: np.ndarray, guard: dict, side: str) -> np.ndarray:
    """(B, K) margin per state and output: one value per output, or the value of the state's predicted-value bin."""
    k_out = min(pred.shape[1], len(guard[side]))
    out = np.zeros(pred.shape)
    if "edges" not in guard:
        out[:, :k_out] = np.asarray(guard[side][:k_out], float)
        return out
    for k in range(k_out):
        table = np.asarray(guard[side][k], float)
        idx = np.searchsorted(np.asarray(guard["edges"][k]), np.nan_to_num(pred[:, k], nan=0.0), side="right")
        out[:, k] = table[idx]
    return out


def bounds(pred: np.ndarray, guard: dict) -> tuple[np.ndarray, np.ndarray]:
    """(guarded, optimistic): the outputs moved toward danger by the danger margin, and away by the optimistic one."""
    sign = DANGER_SIGN[:pred.shape[1]]
    return pred + sign * margins(pred, guard, "danger"), pred - sign * margins(pred, guard, "optimistic")


def margin_at(guard: dict, k: int, value: float, side: str = "danger") -> float:
    """The margin applied to output `k` for a state predicted exactly at `value` (e.g. at a limit), for reports."""
    n = len(guard[side])
    return float(margins(np.array([[value] * n], float), guard, side)[0, k])


def crosses(ext: np.ndarray, vmin_pu: float, vmax_pu: float, vuf_limit: float | None = None) -> np.ndarray:
    """Whether outputs break the band or 100% loading (and the VUF limit when one is given), strict as the engine."""
    with np.errstate(invalid="ignore"):
        out = (ext[:, 0] > vmax_pu) | (ext[:, 1] < vmin_pu) | (ext[:, 2] > 100) | (ext[:, 3] > 100)
        if vuf_limit is not None and ext.shape[1] > 4:
            out |= ext[:, 4] > vuf_limit
    return out


def decide(pred: np.ndarray, guard: dict, vmin_pu: float, vmax_pu: float, p_fail: np.ndarray | None = None,
           failure_threshold: float = FAILURE_THRESHOLD, vuf_limit: float | None = None) -> dict:
    guarded, optimistic = bounds(pred, guard)
    checked = 5 if vuf_limit is not None and pred.shape[1] > 4 else 4
    risky = crosses(guarded, vmin_pu, vmax_pu, vuf_limit) | ~np.isfinite(guarded[:, :checked]).all(axis=1)
    if p_fail is not None:
        risky |= p_fail > failure_threshold
    return {"guarded": guarded, "optimistic": optimistic, "risky": risky,
            "clearly_unsafe": crosses(optimistic, vmin_pu, vmax_pu, vuf_limit),
            "point_unsafe": crosses(pred, vmin_pu, vmax_pu, vuf_limit)}


def limit_margins(guard: dict) -> dict:
    """Danger margins where decisions are made: at each rule's voltage limits (volts) and at 100% loading (points)."""
    from engine.rules import get_rule
    out = {}
    for rid in ("up_2005", "pm10"):
        r = get_rule(rid)
        out[rid] = {"v_max_v": round(margin_at(guard, 0, r.vmax_pu) * r.nominal_v, 3),
                    "v_min_v": round(margin_at(guard, 1, r.vmin_pu) * r.nominal_v, 3)}
    out["line_pts"], out["trafo_pts"] = round(margin_at(guard, 2, 100.0), 3), round(margin_at(guard, 3, 100.0), 3)
    if len(guard["danger"]) > 4:
        out["vuf_pts_at_2pct"] = round(margin_at(guard, 4, 2.0), 3)
    return out
