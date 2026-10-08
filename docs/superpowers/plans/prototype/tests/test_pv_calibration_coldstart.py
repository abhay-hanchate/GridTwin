import numpy as np
import pandas as pd
import pytest

from ml import coldstart, pv_calibration

IDX = pd.date_range("2025-03-01", periods=24 * 40, freq="h")


def _modelled():
    hour = IDX.hour.to_numpy()
    return pd.Series(np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * 0.8, index=IDX)


def test_yield_factor_recovers_the_true_loss_and_ignores_outage_days():
    modelled = _modelled()
    measured = modelled * 72 * 0.9                             # a 72 kWp plant that yields 10% less than modelled
    measured[(IDX >= "2025-03-10") & (IDX < "2025-03-12")] = 0.0   # two outage days
    r = pv_calibration.yield_factor(measured, 72, modelled)
    assert r["factor"] == pytest.approx(0.9, abs=1e-3) and r["usable"] and r["n_days"] == 40


def test_too_few_days_are_not_usable_and_no_data_returns_the_neutral_factor():
    modelled = _modelled()
    short = pv_calibration.yield_factor((modelled * 10)[: 24 * 5], 10, modelled)
    assert short["factor"] == pytest.approx(1.0, abs=1e-3) and short["usable"] is False
    empty = pv_calibration.yield_factor(pd.Series(dtype=float), 10, modelled)
    assert empty == {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}


def test_plant_csv_is_read_in_watts_or_kilowatts(tmp_path):
    f = tmp_path / "plant.csv"
    pd.DataFrame({"ts": pd.date_range("2025-03-01 10:00", periods=4, freq="30min"), "power": [2000, 4000, 6000, 8000]}).to_csv(f, index=False)
    s = pv_calibration.read_plant_csv(f, "ts", "power", unit="W")
    assert s.iloc[0] == pytest.approx(3.0) and s.iloc[1] == pytest.approx(7.0)


def test_factor_starts_at_the_prior_and_moves_toward_the_roof_own_readings():
    assert coldstart.shrunk_factor(None, 0) == 1.0
    assert coldstart.shrunk_factor(0.8, 0, prior=0.95) == 0.95
    f10, f60, f600 = (coldstart.shrunk_factor(0.8, n) for n in (10, 60, 600))
    assert 1.0 > f10 > f60 > f600 > 0.8 and f600 == pytest.approx(0.8, abs=0.015)


def test_new_roof_forecast_scales_with_size_and_widens_while_history_is_short():
    per = pd.DataFrame({"p10": [0.2], "p50": [0.4], "p90": [0.6]}, index=pd.DatetimeIndex(["2025-05-01 12:00"]))
    new, old = coldstart.forecast_new_system(per, 3.0, n_days=0), coldstart.forecast_new_system(per, 3.0, n_days=300)
    assert new.p50.iloc[0] == pytest.approx(1.2) and (new.p90 - new.p10).iloc[0] > (old.p90 - old.p10).iloc[0]
    assert new.p10.iloc[0] < old.p10.iloc[0] < old.p50.iloc[0] < old.p90.iloc[0] < new.p90.iloc[0]
    assert coldstart.forecast_new_system(per, 3.0, factor=0.9, n_days=300).p50.iloc[0] == pytest.approx(1.08)


def test_calibrate_script_recovers_the_loss_from_files(tmp_path):
    import json

    from engine import config, profiles
    from scripts.calibrate_pv import calibrate
    idx = pd.date_range("2025-03-01", periods=24 * 30, freq="h")
    clear = profiles.clearsky_ghi(idx).to_numpy()
    hourly = {"time": [t.isoformat() for t in idx], "shortwave_radiation": list(clear), "direct_normal_irradiance": list(clear * 0.7),
              "diffuse_radiation": list(clear * 0.2), "temperature_2m": [30.0] * len(idx), "cloud_cover": [10.0] * len(idx),
              "wind_speed_10m": [2.0] * len(idx)}
    weather = tmp_path / "w.json"
    weather.write_text(json.dumps({"hourly": hourly}))
    site = config.Site(12.97, 77.59, 900)
    modelled = profiles.pv_hourly(profiles.read_weather(weather), site)
    csv = tmp_path / "plant.csv"
    pd.DataFrame({"ts": idx, "kw": (modelled * 72 * 0.85).to_numpy()}).to_csv(csv, index=False)
    r = calibrate(csv, "ts", "kw", "kW", 72.0, weather, site)
    assert r["factor"] == pytest.approx(0.85, abs=0.01) and r["usable"] and r["n_days"] >= 25
