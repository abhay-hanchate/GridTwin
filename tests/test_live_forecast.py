from datetime import date, datetime, timedelta, timezone

import pandas as pd
from fastapi.testclient import TestClient

import backend.main as api
from engine import config
from ml.live_forecast import predict_solar, tomorrow_local, weather_frame

client = TestClient(api.app)


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


def _live_result(target: date) -> dict:
    return {
        "target": "solar",
        "unit": "kW per installed kW",
        "date": target.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weather_source": "Open-Meteo live forecast",
        "weather_url": "https://api.open-meteo.com/test",
        "model": "GridTwin LightGBM quantile ensemble",
        "points": [
            {"t": f"{i // 4:02d}:{(i % 4) * 15:02d}", "p10": 0.1, "p50": 0.2, "p90": 0.3}
            for i in range(96)
        ],
    }


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


def test_live_forecast_api_contract_without_network(monkeypatch):
    target = date(2026, 9, 30)
    monkeypatch.setattr(api, "live_solar_forecast", lambda requested: _live_result(requested))
    response = client.get("/api/live-forecast", params={"date": target.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == target.isoformat()
    assert body["model"] == "GridTwin LightGBM quantile ensemble"
    assert len(body["points"]) == 96


def test_live_warning_api_contract_without_network(monkeypatch):
    target = date(2026, 9, 30)
    monkeypatch.setattr(api, "live_solar_forecast", lambda requested: _live_result(requested))
    monkeypatch.setattr(api, "live_warning", lambda date_value, frame, risk, band: {
        "date": date_value,
        "risk_band": risk,
        "demand_mode": "historical_proxy",
        "demand_proxy_date": "2019-09-30",
        "pv_share": 1.0,
        "band": band,
        "cases": {key: {"violation_steps": 4, "max_vm_pu": 1.08,
                         "first_unsafe": "12:00", "unsafe_times": ["12:00"]}
                  for key in ("p10", "p50", "p90")},
        "predicted": {"violation_steps": 4, "max_vm_pu": 1.08,
                       "first_unsafe": "12:00", "unsafe_times": ["12:00"]},
        "provenance": {"reference": "unavailable until the target day has occurred"},
    })
    response = client.get("/api/live-early-warning", params={"date": target.isoformat(), "risk": "p90"})
    assert response.status_code == 200
    assert response.json()["predicted"]["violation_steps"] == 4


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
