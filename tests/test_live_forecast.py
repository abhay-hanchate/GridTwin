"""Round 1 solar model, still the base of solar v2's live inference (ml/live_solar_v2.py)."""
from datetime import date, datetime, timezone

import pandas as pd

from engine import config
from ml.live_forecast import predict_solar, tomorrow_local, weather_frame


def _weather_payload(target: date) -> dict:
    times = pd.date_range(target.isoformat(), periods=48, freq="h")
    hourly = {"time": [timestamp.isoformat() for timestamp in times]}
    defaults = {
        "shortwave_radiation": 500.0,
        "direct_normal_irradiance": 600.0,
        "diffuse_radiation": 100.0,
        "temperature_2m": 30.0,
        "cloud_cover": 20.0,
        "wind_speed_10m": 8.0,
    }
    for name in config.WEATHER_VARS:
        hourly[name] = [defaults[name]] * 48
    return {"hourly": hourly}


def test_tomorrow_uses_mathura_local_date():
    late_utc = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)
    assert tomorrow_local(late_utc) == date(2026, 10, 1)


def test_live_weather_and_frozen_models_produce_96_ordered_intervals():
    target = date(2026, 9, 30)
    weather = weather_frame(_weather_payload(target), target)
    forecast = predict_solar(weather, target)
    assert len(forecast) == 96
    assert list(forecast.columns) == ["p10", "p50", "p90"]
    assert (forecast["p10"] <= forecast["p50"]).all()
    assert (forecast["p50"] <= forecast["p90"]).all()
    assert forecast.min().min() >= 0 and forecast.max().max() <= 1


def test_weather_schema_rejects_missing_fields():
    target = date(2026, 9, 30)
    payload = _weather_payload(target)
    del payload["hourly"]["cloud_cover"]
    try:
        weather_frame(payload, target)
    except RuntimeError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing weather field was accepted")
