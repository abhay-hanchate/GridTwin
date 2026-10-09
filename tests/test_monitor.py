import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ml.live_solar_v2 import _conformal_q
from scripts import monitor


def _day_curve(index: pd.DatetimeIndex) -> np.ndarray:
    hour = index.hour + index.minute / 60
    return np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * 0.7


def _history(days: int, *, noise: float, bias: float = 0.0, half_width: float = 0.065, seed: int = 0):
    """Issued forecasts (15 min, already widened by q_used) and hourly realised truth with the given error."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-08-01", periods=days * 96, freq="15min")
    p50 = pd.Series(_day_curve(idx), index=idx)
    q_used = 0.02
    log = pd.DataFrame({"p10": (p50 - half_width).clip(lower=0), "p50": p50, "p90": p50 + half_width,
                        "q_used": q_used}, index=idx)
    hourly = idx[idx.minute == 0]
    truth = (p50[hourly] + bias + rng.normal(0, noise, len(hourly))).clip(lower=0)
    truth[p50[hourly] == 0] = 0.0
    return log, truth


def test_healthy_forecasts_raise_no_warning_and_clear_a_stale_one(tmp_path):
    log, truth = _history(40, noise=0.05)
    (tmp_path / "WARN").write_text("old")
    out = monitor.run_checks(log, truth, as_of=date(2026, 9, 10), baseline_mae=0.04, window_days=30, out_dir=tmp_path)
    assert out["warn"] is False and not (tmp_path / "WARN").exists()
    assert 0.70 <= out["coverage_14d"] <= 0.90


def test_synthetic_drift_triggers_the_warning(tmp_path):
    log, truth = _history(40, noise=0.05, bias=0.15)               # the sky changed; forecasts did not
    out = monitor.run_checks(log, truth, as_of=date(2026, 9, 10), baseline_mae=0.04, window_days=30, out_dir=tmp_path)
    assert out["warn"] is True
    reasons = (tmp_path / "WARN").read_text()
    assert "coverage" in reasons and "MAE" in reasons


def test_mae_rise_alone_is_enough(tmp_path):
    log, truth = _history(40, noise=0.05)                          # coverage fine, MAE about double the baseline
    out = monitor.run_checks(log, truth, as_of=date(2026, 9, 10), baseline_mae=0.02, window_days=30, out_dir=tmp_path)
    assert out["warn"] is True and len(out["reasons"]) == 1
    assert "MAE" in out["reasons"][0]


def test_conformal_width_uses_only_the_window_before_the_day(tmp_path):
    log, truth = _history(60, noise=0.05)
    as_of = date(2026, 9, 1)
    q = monitor.conformal_width(log, truth, as_of=as_of, window_days=30)
    later = truth.copy()
    later[later.index >= "2026-09-01"] += 0.5                      # what happens after as_of cannot change the width
    earlier = truth.copy()
    earlier[earlier.index < "2026-08-02"] += 0.5                   # nor what happened before the window
    assert monitor.conformal_width(log, later, as_of=as_of, window_days=30) == q
    assert monitor.conformal_width(log, earlier, as_of=as_of, window_days=30) == q


def test_widening_is_undone_before_scoring():
    """The log stores widened intervals; the width is re-estimated from the raw ones, so it does not compound."""
    log, truth = _history(40, noise=0.05)
    q1 = monitor.conformal_width(log, truth, as_of=date(2026, 9, 10), window_days=30)
    wider = log.assign(p10=(log["p10"] - 0.1).clip(lower=0), p90=log["p90"] + 0.1, q_used=log["q_used"] + 0.1)
    q2 = monitor.conformal_width(wider, truth, as_of=date(2026, 9, 10), window_days=30)
    assert q2 == pytest.approx(q1, abs=0.01)


def test_state_file_is_what_live_inference_reads(tmp_path):
    log, truth = _history(40, noise=0.05)
    out = monitor.run_checks(log, truth, as_of=date(2026, 9, 10), baseline_mae=0.04, window_days=30, out_dir=tmp_path)
    q, source = _conformal_q({"conformal_q": 0.99}, tmp_path / "conformal_state.json")
    assert q == pytest.approx(out["q"]) and "2026-09-10" in source
    assert json.loads((tmp_path / "conformal_state.json").read_text())["window_days"] == 30


def test_too_little_history_keeps_the_previous_width(tmp_path):
    log, truth = _history(2, noise=0.05)
    out = monitor.run_checks(log, truth, as_of=date(2026, 8, 3), baseline_mae=0.04, window_days=30, out_dir=tmp_path)
    assert out["q"] is None and not (tmp_path / "conformal_state.json").exists()


def test_log_forecast_replaces_a_day_instead_of_duplicating_it(tmp_path):
    path = tmp_path / "log.parquet"
    idx = pd.date_range("2026-10-10", periods=96, freq="15min")
    first = pd.DataFrame({"p10": 0.1, "p50": 0.2, "p90": 0.3}, index=idx)
    monitor.log_forecast(first, 0.02, path)
    monitor.log_forecast(first.assign(p50=0.25), 0.03, path)
    log = pd.read_parquet(path)
    assert len(log) == 96 and log["p50"].iloc[0] == 0.25 and log["q_used"].iloc[0] == 0.03


def test_state_holds_one_width_per_season_from_all_earlier_days_of_that_season(tmp_path):
    summer_log, summer_truth = _history(30, noise=0.02, seed=1)                 # August: monsoon, small errors
    autumn_log, autumn_truth = _history(30, noise=0.10, seed=2)                 # shifted to October: post-monsoon
    shift = pd.Timedelta(days=61)
    autumn_log.index += shift
    autumn_truth.index += shift
    log = pd.concat([summer_log, autumn_log])
    truth = pd.concat([summer_truth, autumn_truth])
    out = monitor.run_checks(log, truth, as_of=date(2026, 11, 1), baseline_mae=0.05, window_days=30, out_dir=tmp_path)
    by_season = json.loads((tmp_path / "conformal_state.json").read_text())["q_by_season"]
    assert set(by_season) == {"monsoon", "post_monsoon"} and out["q_by_season"] == by_season
    assert by_season["post_monsoon"] > by_season["monsoon"]
