"""Drift monitor (P10.6): score the issued solar forecasts against realised PV, refresh the interval width, warn.

Usage:  python -m scripts.monitor [--as-of YYYY-MM-DD]      (run nightly, after the forecast is logged)

- The nightly run logs every issued forecast with the conformal width it used (`log_forecast`).
- The widths are re-estimated from the *raw* intervals (the logged width removed again): one per season from every
  earlier logged day of that season (the shipped method), plus one over the last `conformal_window_days` as the
  fallback; both go to data/monitor/conformal_state.json, which ml.live_solar_v2 reads.
- data/monitor/WARN is written when coverage over 14 days leaves 70 to 90% or MAE rises more than 25% above the
  model card baseline (the manifest's 2025 MAE); it is removed again when both are healthy.

Truth is ERA5-driven PV, the same reference the model was trained on; ERA5 arrives a few days late, so recent days
are scored once they exist.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from engine import config, profiles
from ml import solar_v2
from ml.conformal import conformal_q

MONITOR_DIR = config.ROOT / "data" / "monitor"
LOG_PATH = MONITOR_DIR / "solar_forecast_log.parquet"
MANIFEST = config.ROOT / "ml" / "models" / "solar_v2_manifest.json"
COVERAGE_DAYS = 14
COVERAGE_BAND = (0.70, 0.90)
MAE_RISE = 0.25
MIN_POINTS = 50
ALPHA = 0.2


def log_forecast(forecast: pd.DataFrame, q_used: float, path: Path = LOG_PATH) -> None:
    """Append one issued forecast (P10/P50/P90 after widening) and the width used; a re-issued day replaces the old."""
    new = forecast[["p10", "p50", "p90"]].astype(float).assign(q_used=float(q_used))
    if path.exists():
        old = pd.read_parquet(path)
        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(path)


def _paired(log: pd.DataFrame, truth: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Daylight hours with both a forecast and realised PV: (issued interval, raw interval, truth)."""
    issued = log.reindex(truth.index).dropna(subset=["p50"])
    y = truth.reindex(issued.index)
    ok = y.notna() & ((issued["p50"] > 0) | (y > 0))
    issued, y = issued[ok], y[ok]
    # Undo the widening. Where P10 was clipped at zero the raw lower end is overstated, which errs on the wide side.
    raw = pd.DataFrame({"p10": np.minimum(issued["p10"] + issued["q_used"], issued["p50"]), "p50": issued["p50"],
                        "p90": np.maximum(issued["p90"] - issued["q_used"], issued["p50"])}, index=issued.index)
    return issued, raw, y


def _between(index: pd.DatetimeIndex, as_of: date, days: int) -> np.ndarray:
    end = pd.Timestamp(as_of)
    return (index >= end - pd.Timedelta(days=days)) & (index < end)


def conformal_width(log: pd.DataFrame, truth: pd.Series, *, as_of: date, window_days: int) -> float | None:
    """Width for forecasts issued on `as_of`, from the raw errors of the `window_days` days before it; None if too few."""
    _, raw, y = _paired(log, truth)
    sel = _between(raw.index, as_of, window_days)
    if sel.sum() < MIN_POINTS:
        return None
    return round(conformal_q(raw[sel], y[sel], ALPHA), 6)


def season_widths(log: pd.DataFrame, truth: pd.Series, *, as_of: date) -> dict:
    """One width per season from every earlier logged day of that season (the shipped interval method)."""
    _, raw, y = _paired(log, truth)
    earlier = raw.index < pd.Timestamp(as_of)
    seasons = pd.Series(solar_v2.season_of_index(raw.index), index=raw.index)
    out = {}
    for s in sorted(seasons[earlier].unique()):
        sel = earlier & (seasons == s).to_numpy()
        if sel.sum() >= MIN_POINTS:
            out[s] = round(conformal_q(raw[sel], y[sel], ALPHA), 6)
    return out


def recent_scores(log: pd.DataFrame, truth: pd.Series, *, as_of: date, days: int = COVERAGE_DAYS) -> dict:
    issued, _, y = _paired(log, truth)
    sel = _between(issued.index, as_of, days)
    f, yy = issued[sel], y[sel]
    if not len(f):
        return {"n": 0, "coverage": None, "mae": None}
    return {"n": int(len(f)), "coverage": round(float(((yy >= f["p10"]) & (yy <= f["p90"])).mean()), 3),
            "mae": round(float((f["p50"] - yy).abs().mean()), 4)}


def run_checks(log: pd.DataFrame, truth: pd.Series, *, as_of: date, baseline_mae: float, window_days: int,
               out_dir: Path = MONITOR_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    q = conformal_width(log, truth, as_of=as_of, window_days=window_days)
    q_by_season = season_widths(log, truth, as_of=as_of)
    if q is not None:      # too little history keeps whatever width was there (state file or manifest)
        (out_dir / "conformal_state.json").write_text(json.dumps(
            {"q": q, "q_by_season": q_by_season, "as_of": as_of.isoformat(), "window_days": window_days}, indent=2),
            encoding="utf-8")
    s = recent_scores(log, truth, as_of=as_of)
    reasons = []
    if s["n"] >= MIN_POINTS:
        lo, hi = COVERAGE_BAND
        if not lo <= s["coverage"] <= hi:
            reasons.append(f"coverage {s['coverage']:.1%} over {COVERAGE_DAYS} days is outside {lo:.0%} to {hi:.0%}")
        if s["mae"] > baseline_mae * (1 + MAE_RISE):
            reasons.append(f"MAE {s['mae']:.4f} over {COVERAGE_DAYS} days is more than {MAE_RISE:.0%} above "
                           f"the model card baseline {baseline_mae:.4f}")
    warn = out_dir / "WARN"
    if reasons:
        warn.write_text(f"solar forecast drift as of {as_of.isoformat()}\n" + "\n".join(reasons) + "\n", encoding="utf-8")
    elif warn.exists():
        warn.unlink()
    return {"as_of": as_of.isoformat(), "q": q, "q_by_season": q_by_season, "coverage_14d": s["coverage"], "mae_14d": s["mae"], "n_14d": s["n"],
            "warn": bool(reasons), "reasons": reasons}


def realised_pv(start: date, end: date, district: str = "mathura") -> pd.Series:
    """Hourly ERA5-driven PV (kW per kWp) from the Open-Meteo archive; days not yet in ERA5 come back missing."""
    site = config.SITES[district]
    params = {"latitude": site.latitude, "longitude": site.longitude, "start_date": start.isoformat(),
              "end_date": end.isoformat(), "hourly": ",".join(config.WEATHER_VARS), "timezone": config.TIMEZONE,
              "models": "era5"}
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=120)
    r.raise_for_status()
    w = pd.DataFrame(r.json()["hourly"])
    w["time"] = pd.to_datetime(w["time"])
    w = w.set_index("time").apply(pd.to_numeric, errors="coerce")
    complete = w["shortwave_radiation"].notna()
    return profiles.pv_hourly(w[complete], site).reindex(w.index)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = ap.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    window = int(manifest["conformal_window_days"])
    if not LOG_PATH.exists():
        raise SystemExit(f"no forecasts logged yet ({LOG_PATH}); the nightly run logs them")
    log = pd.read_parquet(LOG_PATH)
    truth = realised_pv(args.as_of - timedelta(days=max(window, COVERAGE_DAYS) + 1), args.as_of - timedelta(days=1))
    out = run_checks(log, truth, as_of=args.as_of, baseline_mae=float(manifest["scores_2025"]["mae_p50"]),
                     window_days=window)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
