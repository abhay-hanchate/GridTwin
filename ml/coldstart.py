"""B4: forecast a rooftop that has no history yet, and improve as its own readings arrive.

A new system starts from the district's per-kWp forecast times its installed kWp. Its yield factor starts at the
prior (1.0, or a plant-calibrated value from `ml.pv_calibration`) and moves toward what its own meter shows,
weighted by the number of observed days. The interval is widened while the factor is still uncertain.
The widening constant (15% of output at zero history) is an ASSUMPTION, not a measured quantity.
"""
from __future__ import annotations

import pandas as pd

PRIOR_WEIGHT_DAYS = 30.0
INITIAL_SPREAD = 0.15


def shrunk_factor(observed_ratio: float | None, n_days: int, prior: float = 1.0, prior_weight_days: float = PRIOR_WEIGHT_DAYS) -> float:
    """Posterior-style blend: (n x observed + w x prior) / (n + w)."""
    if observed_ratio is None or n_days <= 0:
        return float(prior)
    return float((n_days * observed_ratio + prior_weight_days * prior) / (n_days + prior_weight_days))


def uncertainty_spread(n_days: int, prior_weight_days: float = PRIOR_WEIGHT_DAYS) -> float:
    """Extra relative width of the interval; falls from INITIAL_SPREAD toward zero as days accumulate."""
    return INITIAL_SPREAD * prior_weight_days / (max(n_days, 0) + prior_weight_days)


def forecast_new_system(per_kwp: pd.DataFrame, kwp: float, *, factor: float = 1.0, n_days: int = 0) -> pd.DataFrame:
    """P10/P50/P90 in kW for one system of `kwp` installed kilowatts, from the district forecast per kWp."""
    spread = uncertainty_spread(n_days)
    out = pd.DataFrame(index=per_kwp.index)
    out["p10"] = per_kwp["p10"] * kwp * factor * (1 - spread)
    out["p50"] = per_kwp["p50"] * kwp * factor
    out["p90"] = per_kwp["p90"] * kwp * factor * (1 + spread)
    return out
