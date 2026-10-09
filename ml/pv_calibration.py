"""A7: calibrate the modelled PV yield against a measured plant (kW per installed kWp).

The modelled yield comes from pvlib PVWatts with a flat 14% system loss. A measured plant tells us whether that
loss assumption is too kind or too harsh. The factor is a median of daily ratios over productive hours, so one cloudy
afternoon or an outage does not move it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MIN_MODELLED_KW_PER_KWP = 0.25       # only hours when the sun is clearly producing
MIN_HOURS_PER_DAY = 4
MIN_DAYS = 20


def read_plant_csv(path: Path, timestamp_col: str, power_col: str, *, unit: str = "kW") -> pd.Series:
    """Hourly mean power in kW from a plant file. `unit` is kW or W. Timestamps are taken as local time (IST)."""
    df = pd.read_csv(path, parse_dates=[timestamp_col])
    scale = {"kW": 1.0, "W": 1e-3}[unit]
    s = pd.to_numeric(df.set_index(timestamp_col)[power_col], errors="coerce") * scale
    return s.resample("h").mean().rename("measured_kw")


def yield_factor(measured_kw: pd.Series, kwp: float, modelled_kw_per_kwp: pd.Series) -> dict:
    """Ratio of measured to modelled energy per day over productive hours, and its spread.

    Returns {"factor", "p10", "p90", "n_days", "usable"}; `usable` is False when there are too few days to trust.
    """
    both = pd.concat([measured_kw / kwp, modelled_kw_per_kwp], axis=1, keys=["m", "p"]).dropna()
    both = both[both["p"] >= MIN_MODELLED_KW_PER_KWP]
    if both.empty:
        return {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}
    daily = both.groupby(both.index.normalize()).agg(m=("m", "sum"), p=("p", "sum"), n=("m", "size"))
    daily = daily[daily["n"] >= MIN_HOURS_PER_DAY]
    ratio = (daily["m"] / daily["p"]).replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}
    return {"factor": round(float(ratio.median()), 4), "p10": round(float(ratio.quantile(0.1)), 4),
            "p90": round(float(ratio.quantile(0.9)), 4), "n_days": int(len(ratio)), "usable": bool(len(ratio) >= MIN_DAYS)}
