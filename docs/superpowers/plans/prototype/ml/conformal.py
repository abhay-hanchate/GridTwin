"""Split-conformal adjustment of a P10-P90 interval on a held-out calibration window."""
from __future__ import annotations

import numpy as np
import pandas as pd


def conformal_q(pred: pd.DataFrame, y: pd.Series, alpha: float = 0.2) -> float:
    """Amount by which both ends must move so the interval covers about 1 - alpha of calibration points."""
    scores = np.maximum(pred["p10"].to_numpy() - y.to_numpy(), y.to_numpy() - pred["p90"].to_numpy())
    n = len(scores)
    k = min(n, int(np.ceil((n + 1) * (1 - alpha))))
    return float(np.sort(scores)[k - 1])


def apply_conformal(pred: pd.DataFrame, q: float, floor: float | None = None) -> pd.DataFrame:
    out = pred.copy()
    out["p10"] = pred["p10"] - q
    out["p90"] = pred["p90"] + q
    if floor is not None:
        out[["p10", "p50", "p90"]] = out[["p10", "p50", "p90"]].clip(lower=floor)
    out["p10"] = np.minimum(out["p10"], out["p50"])
    out["p90"] = np.maximum(out["p90"], out["p50"])
    return out
