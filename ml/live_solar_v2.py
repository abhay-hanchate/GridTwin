"""Live next-day solar inference for v2: several NWP models from Open-Meteo, frozen v2 boosters, current conformal width.

The conformal width comes from `data/monitor/conformal_state.json` when the nightly monitor has written one
(the realised errors of the manifest's conformal window); otherwise the value stored in the model manifest is used and the result
says so (`interval_source`).

Usage: python -m ml.live_solar_v2 [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from engine import config
from ml import solar_v2
from ml.live_forecast import LiveForecastError, tomorrow_local

FORECAST_API = "https://api.open-meteo.com/v1/forecast"
MODEL_DIR = solar_v2.MODEL_DIR
STATE_PATH = config.ROOT / "data" / "monitor" / "conformal_state.json"
MIN_MODELS = 3


def request_params(target: date, models: tuple[str, ...] = solar_v2.MODELS, site: config.Site | None = None) -> dict:
    site = site or config.SITES["mathura"]
    return {"latitude": site.latitude, "longitude": site.longitude, "timezone": config.TIMEZONE,
            "start_date": target.isoformat(), "end_date": (target + timedelta(days=1)).isoformat(),
            "hourly": ",".join(config.WEATHER_VARS), "models": ",".join(models)}


def fetch_payload(target: date, site: config.Site | None = None) -> dict:
    try:
        r = requests.get(FORECAST_API, params=request_params(target, site=site), timeout=30)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveForecastError(f"Open-Meteo multi-model request failed: {exc}") from exc


def frames_from_payload(payload: dict, target: date, models: tuple[str, ...] = solar_v2.MODELS) -> dict[str, pd.DataFrame]:
    """One two-day hourly frame per model that returned complete irradiance; others are left out."""
    try:
        table = pd.DataFrame(payload["hourly"])
        table["time"] = pd.to_datetime(table["time"], errors="raise")
        table = table.set_index("time")
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveForecastError("Open-Meteo response has no valid hourly table") from exc
    start = pd.Timestamp(target)
    table = table[(table.index >= start) & (table.index < start + pd.Timedelta(days=2))]
    frames = {}
    for m in models:
        cols = {f"{v}_{m}": v for v in config.WEATHER_VARS}
        if not set(cols) <= set(table.columns):
            continue
        frame = table[list(cols)].rename(columns=cols).apply(pd.to_numeric, errors="coerce")
        if len(frame) == 48 and frame["shortwave_radiation"].notna().all():
            frames[m] = frame
    if len(frames) < MIN_MODELS:
        raise LiveForecastError(f"only {len(frames)} NWP models returned complete data; need {MIN_MODELS}")
    return frames


def _conformal_q(manifest: dict, state_path: Path) -> tuple[float, str]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return float(state["q"]), f"monitor state from {state['as_of']}"
    except (OSError, ValueError, KeyError):
        return float(manifest["conformal_q"]), "manifest value from the end of the training year"


def predict_live(frames: dict[str, pd.DataFrame], target: date, model_dir: Path = MODEL_DIR,
                 state_path: Path = STATE_PATH) -> tuple[pd.DataFrame, str]:
    """96 quarter-hour P10/P50/P90 values (kW per installed kW) for `target` and the source of the interval width."""
    manifest_path = model_dir / "solar_v2_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LiveForecastError("solar v2 manifest is unavailable or invalid") from exc
    X = solar_v2.ensemble_features(frames)
    if list(manifest["feature_names"]) != solar_v2.FEATURES:
        raise LiveForecastError("live feature schema does not match the trained model")
    day = X["clearsky_ghi"] > 0
    out = pd.DataFrame(0.0, index=X.index, columns=list(solar_v2.QUANTILES))
    for q in solar_v2.QUANTILES:
        path = model_dir / manifest["model_files"][q]
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise LiveForecastError(f"solar v2 model artifact could not be read: {exc}") from exc
        if hashlib.sha256(blob).hexdigest() != manifest["model_sha256"][q]:
            raise LiveForecastError(f"checksum mismatch for {path.name}")
        out.loc[day, q] = lgb.Booster(model_file=str(path)).predict(X.loc[day, solar_v2.FEATURES])
    out[:] = np.sort(out.to_numpy(), axis=1)
    out = out.add(X["pv_mean"], axis=0).clip(lower=0)
    out[~day] = 0.0
    q_width, source = _conformal_q(manifest, state_path)
    out.loc[day, "p10"] = (out.loc[day, "p10"] - q_width).clip(lower=0)
    out.loc[day, "p90"] = out.loc[day, "p90"] + q_width
    out = out.clip(upper=1.0)
    quarter = out.resample("15min").interpolate("time").loc[target.isoformat()]
    if len(quarter) != 96 or quarter.isna().any().any():
        raise LiveForecastError("live inference did not produce 96 complete intervals")
    return quarter.astype("float32"), source


def live_solar_forecast_v2(target: date | None = None) -> dict:
    target = target or tomorrow_local()
    frames = frames_from_payload(fetch_payload(target), target)
    forecast, source = predict_live(frames, target)
    return {"target": "solar", "unit": "kW per installed kW", "date": target.isoformat(), "model": "GridTwin solar v2",
            "nwp_models": sorted(frames), "interval_source": source,
            "provenance": "modeled: multi-model NWP through pvlib PVWatts plus LightGBM residual quantiles",
            "points": [{"t": ts.strftime("%H:%M"), **{q: round(float(row[q]), 4) for q in solar_v2.QUANTILES}}
                       for ts, row in forecast.iterrows()]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    result = live_solar_forecast_v2(ap.parse_args().date)
    print(json.dumps({"date": result["date"], "nwp_models": result["nwp_models"], "interval_source": result["interval_source"],
                      "peak_p50": max(p["p50"] for p in result["points"])}, indent=2))


if __name__ == "__main__":
    main()
