import numpy as np
import pandas as pd
import pytest

from ml import benchmark

IDX = pd.date_range("2025-01-01", "2025-02-28 23:00", freq="h")


@pytest.fixture(scope="module")
def data():
    rng = np.random.default_rng(3)
    hour = IDX.hour.to_numpy()
    base = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)
    y = pd.Series(base * rng.uniform(0.4, 1.0, len(IDX) // 24)[np.arange(len(IDX)) // 24], index=IDX)
    X = pd.DataFrame({"pv_mean": base * 0.7, "ghi_mean": base * 600, "cloud_mean": 40.0}, index=IDX)
    return X, y


def test_frames_have_a_full_context_and_a_24_hour_future_per_day(data):
    X, y = data
    days = pd.date_range("2025-01-20", "2025-01-25")
    past, future = benchmark.build_frames(X, y, days)
    assert past.id.nunique() == future.id.nunique() == 6
    assert (past.groupby("id").size() == benchmark.CONTEXT_HOURS).all() and (future.groupby("id").size() == 24).all()
    # nothing from the target day leaks into its own context
    first = past[past.id == "2025-01-20"]
    assert first.timestamp.max() == pd.Timestamp("2025-01-19 23:00")
    assert "target" not in future.columns


def test_days_without_enough_context_are_skipped(data):
    X, y = data
    past, future = benchmark.build_frames(X, y, pd.date_range("2025-01-03", "2025-01-05"))      # fewer than 14 days of history
    assert past.empty and future.empty


def test_chronos_wrapper_renames_quantiles_and_clips_at_zero(data):
    X, y = data

    class Fake:
        def predict_df(self, df, future_df, **kw):
            assert kw["prediction_length"] == 24 and kw["quantile_levels"] == [0.1, 0.5, 0.9]
            t = future_df[["id", "timestamp"]].copy()
            t["target_name"], t["predictions"] = "target", 0.0
            t["0.1"], t["0.5"], t["0.9"] = -0.1, 0.2, 0.4
            return t

    past, future = benchmark.build_frames(X, y, pd.date_range("2025-01-20", "2025-01-22"))
    out = benchmark.chronos_forecast(past, future, pipeline=Fake(), batch_days=2)
    assert list(out.columns) == ["p10", "p50", "p90"] and len(out) == 72 and (out.p10 == 0).all() and (out.p90 == 0.4).all()


def test_adoption_needs_a_five_percent_better_wis(data):
    _, y = data
    mask = pd.Series(True, index=IDX)
    good = pd.DataFrame({"p10": y - 0.1, "p50": y, "p90": y + 0.1})
    wide = pd.DataFrame({"p10": y - 0.4, "p50": y, "p90": y + 0.4})
    scores = benchmark.compare(y, mask, {"v2": wide, "foundation": good}, reference="v2")
    assert scores["foundation"]["adopt"] is True and scores["v2"]["adopt"] is False
    almost = benchmark.compare(y, mask, {"v2": good, "foundation": good}, reference="v2")
    assert almost["foundation"]["wis_gain_vs_reference"] == 0 and almost["foundation"]["adopt"] is False


@pytest.mark.realdata
def test_real_benchmark_reports_both_pipelines_on_the_same_hours():
    """Needs the raw files plus torch and chronos-forecasting; the adoption flag is a result, not an expectation."""
    pytest.importorskip("chronos")
    report = benchmark.run()
    a, b = report["scores_2025"]["solar_v2_lightgbm"], report["scores_2025"]["chronos2_with_covariates"]
    assert a["n"] == b["n"] and report["scores_2025"]["solar_v2_lightgbm"]["adopt"] is False


def test_nowcast_pv_reads_day0_irradiance_through_the_same_pv_chain(tmp_path):
    import json

    from ml import solar_v2
    times = pd.date_range("2025-01-10", periods=24, freq="h")
    sun = np.clip(np.sin((times.hour.to_numpy() - 6) / 12 * np.pi), 0, None)
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
              "shortwave_radiation_previous_day0": list(sun * 700), "direct_normal_irradiance_previous_day0": list(sun * 500),
              "diffuse_radiation_previous_day0": list(sun * 100), "temperature_2m_previous_day0": [20.0] * 24,
              "cloud_cover_previous_day0": [10.0] * 24, "wind_speed_10m_previous_day0": [5.0] * 24}
    path = tmp_path / "nowcast.json"
    path.write_text(json.dumps({"hourly": hourly}))
    pv = benchmark.nowcast_pv(path)
    assert len(pv) == 24 and pv.max() > 0.3 and pv.iloc[2] == 0
    frame = pd.DataFrame({k.replace("_previous_day0", ""): v for k, v in hourly.items() if k != "time"}, index=times)
    pd.testing.assert_series_equal(pv, solar_v2._pv(frame), check_names=False, check_freq=False)
