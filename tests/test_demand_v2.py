import numpy as np
import pandas as pd
import pytest

from ml.demand_v2 import baselines, build_features, fit_model, holiday_set, predict, score, street_mean

SMALL = {"n_estimators": 40, "learning_rate": 0.1, "num_leaves": 15, "min_child_samples": 20, "verbose": -1,
         "random_state": 42, "deterministic": True, "force_col_wise": True}


def _y(days=80):
    idx = pd.date_range("2020-01-01", periods=days * 96, freq="15min")
    rng = np.random.default_rng(0)
    daily = 0.4 + 0.15 * np.sin(2 * np.pi * (np.arange(len(idx)) % 96) / 96 - 1.2)
    weekly = 1 + 0.1 * (idx.dayofweek.to_numpy() >= 5)
    return pd.Series(daily * weekly + rng.normal(0, 0.01, len(idx)), index=idx)


def _temp(y):
    return pd.Series(25 + 5 * np.sin(np.arange(len(y)) / 960), index=y.index)


def test_baselines_are_exact_day_and_week_lags():
    y = _y(); b = baselines(y); t = y.index[-1]
    assert b["lag1d"][t] == y[t - pd.Timedelta(days=1)]
    assert b["lag7d"][t] == y[t - pd.Timedelta(days=7)]
    assert b["mean_1d_7d"][t] == pytest.approx((b["lag1d"][t] + b["lag7d"][t]) / 2)


def test_features_ignore_target_day_demand_and_temperature():
    y = _y(); temp = _temp(y); t = y.index[-1]
    before = build_features(y, temp, set())
    y2, t2 = y.copy(), temp.copy()
    y2[t], t2[t] = 99.0, 99.0
    after = build_features(y2, t2, set())
    pd.testing.assert_series_equal(before.loc[t], after.loc[t])


def test_oracle_temperature_is_added_only_on_request():
    y = _y(); temp = _temp(y)
    assert "temp_target" not in build_features(y, temp, set()).columns
    assert "temp_target" in build_features(y, temp, set(), oracle_temp=temp).columns


def test_holiday_flags_mark_the_target_date_and_the_day_after():
    y = _y(); temp = _temp(y)
    X = build_features(y, temp, {pd.Timestamp("2020-02-10").date()})
    assert X.loc["2020-02-10 12:00", "is_holiday"] == 1
    assert X.loc["2020-02-11 12:00", "is_holiday"] == 0 and X.loc["2020-02-11 12:00", "is_holiday_prev"] == 1


def test_holiday_set_knows_diwali_in_uttar_pradesh():
    assert pd.Timestamp("2019-10-27").date() in holiday_set([2019], "UP")


def test_street_mean_needs_enough_meters():
    idx = pd.date_range("2020-01-01", periods=3, freq="15min")
    loads = pd.DataFrame({f"m{i}": [1.0, 1.0, np.nan] for i in range(6)}, index=idx)
    loads.iloc[2, :2] = [1.0, 1.0]
    out = street_mean(loads)
    assert out.iloc[0] == 1.0 and np.isnan(out.iloc[2])


def test_end_to_end_forecast_is_ordered_and_beats_nothing_silly():
    y = _y(); temp = _temp(y)
    train_end = pd.Timestamp("2020-03-01")
    model = fit_model(y, temp, set(), "lag7d", train_end, calib_days=14, params=SMALL)
    frame = predict(model, y, temp, set())
    test = frame[frame.index >= train_end]
    assert (test["p10"] <= test["p50"]).all() and (test["p50"] <= test["p90"]).all()
    s = score(test)
    assert s["n"] > 500 and np.isfinite(s["skill_vs_best_baseline"]) and 0.5 <= s["coverage"] <= 1.0
