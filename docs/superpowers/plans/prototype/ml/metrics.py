"""Forecast scores shared by every model: pinball loss, weighted interval score, coverage, skill."""
from __future__ import annotations

import numpy as np


def pinball(y, preds: dict) -> float:
    """Mean pinball loss over the given quantile levels (keys) and samples."""
    y = np.asarray(y, dtype=float)
    losses = []
    for level, q in preds.items():
        diff = y - np.asarray(q, dtype=float)
        losses.append(np.maximum(level * diff, (level - 1) * diff))
    return float(np.mean(losses))


def wis(y, p10, p50, p90, alpha: float = 0.2) -> float:
    """Weighted interval score for one central 80% interval plus the median (lower is better)."""
    y, lo, med, hi = (np.asarray(a, dtype=float) for a in (y, p10, p50, p90))
    interval = (hi - lo) + (2 / alpha) * np.maximum(lo - y, 0) + (2 / alpha) * np.maximum(y - hi, 0)
    return float(np.mean((0.5 * np.abs(y - med) + (alpha / 2) * interval) / 1.5))


def coverage(y, lo, hi) -> float:
    y, lo, hi = (np.asarray(a, dtype=float) for a in (y, lo, hi))
    return float(np.mean((y >= lo) & (y <= hi)))


def skill(mae: float, base_mae: float) -> float:
    """1 - MAE / baseline MAE: positive means better than the baseline."""
    return 1.0 - mae / base_mae
