"""Live inputs for a real "tomorrow": Person B's day-ahead forecasts, as 96-row P10/P50/P90 frames.

  solar    ml.live_solar_v2   kW per installed kW (five weather models, LightGBM, per-season conformal widths)
  demand   ml.live_dayahead   mean kW per home
  voltage  ml.live_dayahead   grid voltage, converted from volts to per unit of 230 V

The scenario generator draws every scenario from these quantiles and keeps them correlated through its copula.
A date is "live" when it is today or later (local time); earlier dates use the demo inputs in backend.v2.compute.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime, timedelta, timezone

import pandas as pd

NOMINAL_V = 230.0
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> Date:
    return datetime.now(IST).date()


def is_live(date: str) -> bool:
    return pd.Timestamp(date).date() >= today_ist()


def _frame(points: list[dict], scale: float = 1.0) -> pd.DataFrame:
    df = pd.DataFrame(points)[["p10", "p50", "p90"]].astype(float) / scale
    if len(df) != 96:
        raise ValueError(f"expected 96 quarter-hour rows, got {len(df)}")
    return df.reset_index(drop=True)


def live_forecasts(date: str, district: str = "mathura") -> dict:
    """{"solar", "demand", "voltage_pu"} frames plus provenance text, for one live date."""
    from ml import live_dayahead, live_solar_v2
    target = pd.Timestamp(date).date()
    solar, solar_source = live_solar_v2.predict_live(
        live_solar_v2.frames_from_payload(live_solar_v2.fetch_payload(target), target), target)
    try:
        ratio = live_dayahead.current_ratio(target)
    except (OSError, ValueError, KeyError):
        # No UP state-demand history on this machine: run the pattern-only models, the documented default when the
        # UP recorder is not running (docs/DECISIONS.md, owner decisions 9 Oct 2026).
        ratio = float("nan")
    dv = live_dayahead.live_forecast(district, target, ratio=ratio)
    return {
        "solar": solar[["p10", "p50", "p90"]].astype(float).reset_index(drop=True),
        "demand": _frame(dv["demand"]["points"]),
        "voltage_pu": _frame(dv["voltage"]["points"], NOMINAL_V),
        "provenance": {
            "solar": f"modeled: live solar v2 forecast ({solar_source})",
            "demand": f"modeled: live day-ahead demand ({dv['demand']['model']}); {dv['anchor']['note']}",
            "voltage": f"modeled: live day-ahead grid voltage ({dv['voltage']['model']})",
        },
    }
