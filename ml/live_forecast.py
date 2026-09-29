"""Live next-day solar inference using Open-Meteo and frozen LightGBM models.

The weather endpoint is keyless. Model inference is local: Open-Meteo supplies known-future
weather covariates, while the committed LightGBM boosters produce P10/P50/P90 PV output.

Usage: python -m ml.live_forecast [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from engine import config
from ml.forecast import MODEL_DIR, _apply_scale, solar_features

FORECAST_API = "https://api.open-meteo.com/v1/forecast"
MANIFEST_PATH = MODEL_DIR / "solar_manifest.json"
QUANTILES = ("p10", "p50", "p90")
CACHE_SECONDS = 30 * 60


class LiveForecastError(RuntimeError):
    """Raised when live weather or a versioned model artifact is unavailable or invalid."""


def tomorrow_local(now: datetime | None = None) -> date:
    current = now or datetime.now(ZoneInfo(config.TIMEZONE))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(config.TIMEZONE))
    return current.astimezone(ZoneInfo(config.TIMEZONE)).date() + timedelta(days=1)


def _weather_payload(target: date) -> tuple[dict, str]:
    # Fetch one extra day so interpolation produces all four quarter-hours in the last hour.
    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "start_date": target.isoformat(),
        "end_date": (target + timedelta(days=1)).isoformat(),
        "hourly": ",".join(config.WEATHER_VARS),
        "timezone": config.TIMEZONE,
    }
    try:
        response = requests.get(FORECAST_API, params=params, timeout=30)
        response.raise_for_status()
        return response.json(), response.url
    except (requests.RequestException, ValueError) as exc:
        raise LiveForecastError(f"Open-Meteo forecast request failed: {exc}") from exc


def weather_frame(payload: dict, target: date) -> pd.DataFrame:
    """Validate an Open-Meteo response and return two days of naive local hourly weather."""
    try:
        frame = pd.DataFrame(payload["hourly"])
        frame["time"] = pd.to_datetime(frame["time"], errors="raise")
        frame = frame.set_index("time")
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveForecastError("Open-Meteo response has no valid hourly table") from exc

    missing = [column for column in config.WEATHER_VARS if column not in frame]
    if missing:
        raise LiveForecastError(f"Open-Meteo response is missing {missing}")
    frame = frame[list(config.WEATHER_VARS)].apply(pd.to_numeric, errors="coerce")
    start = pd.Timestamp(target)
    end = start + pd.Timedelta(days=2)
    frame = frame[(frame.index >= start) & (frame.index < end)]
    if len(frame) != 48 or frame.isna().any().any():
        raise LiveForecastError("live weather must contain 48 complete hourly rows")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise LiveForecastError("live weather timestamps must be unique and ordered")
    return frame


def _manifest(path: Path = MANIFEST_PATH) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveForecastError("solar model manifest is unavailable or invalid") from exc
    required = {"feature_names", "interval_scale", "model_files", "model_sha256", "training_data"}
    if not required.issubset(manifest):
        raise LiveForecastError("solar model manifest is incomplete")
    return manifest


def predict_solar(weather: pd.DataFrame, target: date, model_dir: Path = MODEL_DIR) -> pd.DataFrame:
    """Run frozen quantile boosters and return a complete 15-minute target-day forecast."""
    manifest = _manifest(model_dir / "solar_manifest.json")
    features = solar_features(weather)
    feature_names = manifest["feature_names"]
    if list(features.columns) != feature_names:
        raise LiveForecastError("live feature schema does not match the trained model")

    daylight = features["clearsky_ghi"] > 0
    hourly = pd.DataFrame(0.0, index=features.index, columns=QUANTILES)
    try:
        for quantile in QUANTILES:
            model_path = model_dir / manifest["model_files"][quantile]
            digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if digest != manifest["model_sha256"][quantile]:
                raise LiveForecastError(f"checksum mismatch for {model_path.name}")
            booster = lgb.Booster(model_file=str(model_path))
            hourly.loc[daylight, quantile] = booster.predict(features.loc[daylight, feature_names])
    except LiveForecastError:
        raise
    except (lgb.basic.LightGBMError, OSError) as exc:
        raise LiveForecastError(f"solar model artifact could not be loaded: {exc}") from exc

    hourly = hourly.clip(lower=0)
    hourly.loc[:, :] = np.sort(hourly.to_numpy(), axis=1)
    hourly = _apply_scale(hourly, float(manifest["interval_scale"])).clip(lower=0, upper=1)
    quarter_hourly = hourly.resample("15min").interpolate("time").loc[target.isoformat()]
    if len(quarter_hourly) != 96 or quarter_hourly.isna().any().any():
        raise LiveForecastError("live inference did not produce 96 complete intervals")
    return quarter_hourly.astype("float32")


@lru_cache(maxsize=8)
def _cached_live_forecast(target_iso: str, refresh_bucket: int) -> dict:
    del refresh_bucket  # It only bounds the cache lifetime through the cache key.
    target = date.fromisoformat(target_iso)
    payload, source_url = _weather_payload(target)
    weather = weather_frame(payload, target)
    forecast = predict_solar(weather, target)
    return {
        "target": "solar",
        "unit": "kW per installed kW",
        "date": target_iso,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weather_source": "Open-Meteo live forecast",
        "weather_url": source_url,
        "model": "GridTwin LightGBM quantile ensemble",
        "points": [
            {"t": timestamp.strftime("%H:%M"), **{q: round(float(row[q]), 4) for q in QUANTILES}}
            for timestamp, row in forecast.iterrows()
        ],
    }


def live_solar_forecast(target: date | None = None) -> dict:
    target = target or tomorrow_local()
    return _cached_live_forecast(target.isoformat(), int(time.time() // CACHE_SECONDS))


def frame_from_result(result: dict) -> pd.DataFrame:
    index = pd.to_datetime([f"{result['date']} {point['t']}" for point in result["points"]])
    return pd.DataFrame(
        [{q: point[q] for q in QUANTILES} for point in result["points"]], index=index
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    result = live_solar_forecast(args.date)
    peak = max(point["p50"] for point in result["points"])
    print(json.dumps({
        "date": result["date"], "points": len(result["points"]),
        "peak_p50_kw_per_kwp": peak, "model": result["model"],
    }, indent=2))


if __name__ == "__main__":
    main()
