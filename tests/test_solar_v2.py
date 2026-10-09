import numpy as np
import pandas as pd
import pytest

from engine import profiles
from ml import solar_v2

IDX = pd.date_range("2024-03-01", "2024-09-30 23:00", freq="h")


def _weather(ghi: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"shortwave_radiation": ghi, "direct_normal_irradiance": ghi * 0.7, "diffuse_radiation": ghi * 0.2,
                         "temperature_2m": 30.0, "cloud_cover": 50.0, "wind_speed_10m": 2.0}, index=IDX)


@pytest.fixture(scope="module")
def world():
    """Truth irradiance with day-level cloudiness, and five models that each see it with their own error."""
    rng = np.random.default_rng(0)
    clear = profiles.clearsky_ghi(IDX).to_numpy()
    daily = rng.uniform(0.3, 1.0, len(IDX) // 24 + 1)
    truth = clear * np.repeat(daily, 24)[: len(IDX)]
    frames = {}
    for i, m in enumerate(solar_v2.MODELS):
        err = rng.normal(0, 0.25, len(IDX) // 24 + 1)                   # each model misjudges the day's cloudiness
        frames[m] = _weather(np.clip(truth * (1 + np.repeat(err, 24)[: len(IDX)]), 0, None))
    y = profiles.pv_hourly(_weather(truth))
    return frames, y


def test_availability_reports_the_gate_per_model():
    ghi = np.ones(len(IDX))
    good, late, sparse = _weather(ghi), _weather(ghi), _weather(ghi)
    late.iloc[:100] = np.nan                                            # starts a little late but is complete afterwards
    sparse.iloc[::3] = np.nan                                           # a third of the hours missing
    a = solar_v2.availability({"good": good, "late": late, "sparse": sparse}, test_year=2024)
    assert a.loc["good", "passes"] and a.loc["late", "passes"] and not a.loc["sparse", "passes"]
    assert a.loc["late", "first_valid"] == IDX[100] and a.loc["sparse", "nonnull_since_first"] < 0.7


def test_ensemble_features_ignore_a_missing_model_at_that_hour(world):
    frames, _ = world
    broken = {k: v.copy() for k, v in frames.items()}
    broken["gfs_global"].iloc[5000:5010] = np.nan
    X = solar_v2.ensemble_features(broken)
    assert X.loc[IDX[5003], "n_models"] == 4 and X.loc[IDX[100], "n_models"] == 5
    day = X.index[(X.clearsky_ghi > 0)][:200]
    assert (X.loc[day, "pv_min"] <= X.loc[day, "pv_mean"] + 1e-9).all() and (X.loc[day, "pv_mean"] <= X.loc[day, "pv_max"] + 1e-9).all()


def test_the_ensemble_mean_beats_every_single_model(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    single = {m: float((profiles.pv_hourly(f)[day] - y[day]).abs().mean()) for m, f in frames.items()}
    ensemble = float((X.pv_mean[day] - y[day]).abs().mean())
    assert ensemble < min(single.values())


def test_predictions_are_sorted_non_negative_and_zero_at_night(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    models = solar_v2.fit(X, y, day & (X.index < "2024-07-01"))
    pred = solar_v2.predict(models, X)
    assert (pred.p10 <= pred.p50).all() and (pred.p50 <= pred.p90).all() and (pred.to_numpy() >= 0).all()
    assert (pred[~day].to_numpy() == 0).all()
    X2 = X.copy()
    X2.loc[IDX[3000], "pv_mean"] = np.nan
    assert solar_v2.predict(models, X2).loc[IDX[3000]].isna().all()


def test_rolling_conformal_restores_coverage_and_never_peeks_ahead(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    raw = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-06-01")), X)
    days = pd.date_range("2024-07-15", "2024-09-30")
    out = solar_v2.rolling_conformal(raw, y, day, days, window=30, calibration_start="2024-06-01")
    t = day & (X.index >= "2024-07-15")
    cover = ((y[t] >= out.p10[t]) & (y[t] <= out.p90[t])).mean()
    assert 0.70 <= cover <= 0.90
    # Interval of one day is unchanged when later observations change.
    y_changed = y.copy()
    y_changed[y_changed.index >= "2024-08-20"] += 5.0
    again = solar_v2.rolling_conformal(raw, y_changed, day, days, window=30, calibration_start="2024-06-01")
    same = (again.index < "2024-08-20")
    assert np.allclose(again[same].fillna(-1).to_numpy(), out[same].fillna(-1).to_numpy())


def test_evaluate_reports_gate_g3_against_round_one(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    pred = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-07-01")), X)
    s = solar_v2.evaluate(pred, y, day & (X.index >= "2024-08-01"), {"persistence": y.shift(24)})
    assert {"mae_p50", "p10_p90_coverage", "wis", "skill_vs_persistence", "gate_g3_passes"} <= set(s)
    assert s["gate_g3_passes"] == (s["mae_p50"] < solar_v2.ROUND1_MAE)


@pytest.mark.realdata
def test_real_run_passes_gates_g2_and_g3():
    """Needs data/raw/dayahead_*_mathura_2024_2025.json and era5_mathura_2024_2025.json (scripts/download_solar_v2.py)."""
    report = solar_v2.run()
    s = report["scores_2025"]
    assert set(report["nwp_models_used"]) == set(solar_v2.MODELS)
    assert s["gate_g3_passes"] and s["mae_p50"] < 0.0396
    assert 0.77 <= s["p10_p90_coverage"] <= 0.83 and s["wis"] < 0.029


def test_saved_booster_is_lf_and_its_hash_matches_the_bytes_git_stores(tmp_path):
    """.gitattributes stores ml/models/*.txt with LF; a CRLF file would hash differently after checkout."""
    import hashlib

    import lightgbm as lgb
    import numpy as np

    rng = np.random.default_rng(0)
    model = lgb.LGBMRegressor(n_estimators=5, verbose=-1).fit(rng.normal(size=(50, 2)), rng.normal(size=50))
    path = tmp_path / "m.txt"
    digest = solar_v2.save_booster(model, path)
    data = path.read_bytes()
    assert b"\r\n" not in data
    assert digest == hashlib.sha256(data).hexdigest()


def _grouped_case():
    idx = pd.date_range("2025-01-01", periods=24 * 40, freq="h")
    day = pd.Series(True, index=idx)
    groups = pd.Series(np.where(idx.hour < 12, "a", "b"), index=idx)
    pred = pd.DataFrame({"p10": 0.4, "p50": 0.5, "p90": 0.6}, index=idx)
    y = pd.Series(np.where(groups == "a", 0.55, 0.9), index=idx)        # group b misses by 0.3, group a never misses
    return idx, day, groups, pred, y


def test_grouped_conformal_gives_each_group_its_own_width():
    idx, day, groups, pred, y = _grouped_case()
    out = solar_v2.rolling_conformal_groups(pred, y, day, pd.date_range("2025-01-20", "2025-02-09"), groups, window=30)
    jan25 = out.loc["2025-01-25"]
    assert jan25.loc[jan25.index.hour < 12, "p90"].max() <= 0.6 + 1e-9    # group a needs no widening
    assert jan25.loc[jan25.index.hour >= 12, "p90"].min() == pytest.approx(0.9)


def test_grouped_conformal_never_uses_later_days():
    idx, day, groups, pred, y = _grouped_case()
    days = pd.date_range("2025-01-20", "2025-02-09")
    a = solar_v2.rolling_conformal_groups(pred, y, day, days, groups, window=30)
    later = y.copy()
    later[later.index >= "2025-01-25"] += 0.4
    b = solar_v2.rolling_conformal_groups(pred, later, day, days, groups, window=30)
    pd.testing.assert_frame_equal(a.loc[:"2025-01-24"], b.loc[:"2025-01-24"])


def test_grouped_conformal_falls_back_to_all_hours_for_a_thin_group():
    idx, day, groups, pred, y = _grouped_case()
    groups = groups.where(idx < pd.Timestamp("2025-01-25"), "new")       # a group with no history at all
    out = solar_v2.rolling_conformal_groups(pred, y, day, pd.date_range("2025-01-25", "2025-01-25"), groups, window=30)
    assert out.loc["2025-01-25", "p90"].iloc[0] > 0.6                      # widened from the all-hours pool


def test_scaled_conformal_widens_in_proportion_to_the_spread():
    idx = pd.date_range("2025-01-01", periods=24 * 40, freq="h")
    day = pd.Series(True, index=idx)
    spread = np.where(idx.hour < 12, 0.1, 0.4)
    pred = pd.DataFrame({"p10": 0.5 - spread / 2, "p50": 0.5, "p90": 0.5 + spread / 2}, index=idx)
    y = pd.Series(0.5 + spread, index=idx)                                # every miss is one spread above P90/2
    out = solar_v2.rolling_conformal_scaled(pred, y, day, pd.date_range("2025-01-20", "2025-01-21"), window=30)
    jan20 = out.loc["2025-01-20"]
    narrow = jan20.loc[jan20.index.hour < 12, "p90"].iloc[0] - 0.55
    wide = jan20.loc[jan20.index.hour >= 12, "p90"].iloc[0] - 0.70
    assert wide == pytest.approx(4 * narrow)


def test_sky_class_uses_forecast_clearness():
    X = pd.DataFrame({"ghi_mean": [900.0, 500.0, 100.0, 0.0], "clearsky_ghi": [1000.0, 1000.0, 1000.0, 0.0]})
    assert solar_v2.sky_class(X).tolist() == ["clear", "partly", "cloudy", "night"]
