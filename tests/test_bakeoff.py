import json

import numpy as np
import pandas as pd
import pytest

from scripts import bakeoff


def _row(name, mae, wis, coverage=0.8):
    return {"name": name, "mae_p50": mae, "wis": wis, "p10_p90_coverage": coverage}


def test_season_names_follow_indian_seasons():
    idx = pd.DatetimeIndex(["2025-01-15", "2025-04-15", "2025-07-15", "2025-10-15", "2025-12-15"])
    assert bakeoff.season(idx).tolist() == ["winter", "summer", "monsoon", "post_monsoon", "winter"]


def test_median_rule_keeps_the_simplest_when_the_gain_is_below_the_margin():
    rows = [_row("persistence", 0.046, 0.030), _row("round1", 0.0396, 0.029),
            _row("physics_mean", 0.0335, 0.0220), _row("lgbm_residual", 0.0329, 0.0215)]   # 2.3% better WIS
    out = bakeoff.decide_median(rows, reference="round1", margin=0.03)
    assert out["winner"] == "physics_mean" and out["simplest_beating_reference"] == "physics_mean"


def test_median_rule_picks_the_lowest_wis_when_it_clears_the_margin():
    rows = [_row("round1", 0.0396, 0.029), _row("physics_mean", 0.0335, 0.0230), _row("lgbm_residual", 0.0329, 0.0214)]
    assert bakeoff.decide_median(rows, reference="round1", margin=0.03)["winner"] == "lgbm_residual"


def test_median_rule_keeps_the_reference_when_nothing_beats_it():
    rows = [_row("persistence", 0.046, 0.030), _row("round1", 0.0396, 0.029)]
    out = bakeoff.decide_median(rows, reference="round1", margin=0.03)
    assert out["winner"] == "round1" and out["simplest_beating_reference"] is None


def test_interval_rule_needs_every_season_in_the_band():
    rows = [{"name": "raw", "wis": 0.020, "by_season": {"winter": 0.55, "summer": 0.60}},
            {"name": "conf60", "wis": 0.022, "by_season": {"winter": 0.79, "summer": 0.81}},
            {"name": "conf30", "wis": 0.021, "by_season": {"winter": 0.77, "summer": 0.80}}]
    out = bakeoff.decide_interval(rows, band=(0.78, 0.82))
    assert out["winner"] == "conf60" and out["in_band"] == ["conf60"]


def test_interval_rule_falls_back_to_the_smallest_worst_season_miss():
    rows = [{"name": "a", "wis": 0.020, "by_season": {"winter": 0.70, "summer": 0.80}},
            {"name": "b", "wis": 0.025, "by_season": {"winter": 0.76, "summer": 0.85}}]
    out = bakeoff.decide_interval(rows, band=(0.78, 0.82))
    assert out["winner"] == "b" and out["in_band"] == []


def test_point_forecast_gets_a_rolling_conformal_interval():
    idx = pd.date_range("2025-01-01", periods=24 * 90, freq="h")
    rng = np.random.default_rng(0)
    y = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
    point = (y + rng.normal(0, 0.1, len(idx))).clip(lower=0)      # PV is never negative
    day = pd.Series(True, index=idx)
    out = bakeoff.point_with_conformal(point, y, day, pd.date_range("2025-03-01", "2025-03-31"), window=30)
    march = out.loc["2025-03"]
    assert (march["p10"] <= march["p50"]).all() and (march["p50"] <= march["p90"]).all()
    assert (march["p90"] - march["p10"]).mean() > 0.1
    assert (out.loc["2025-01", "p90"] == out.loc["2025-01", "p10"]).all()     # no pool yet, no widening


def test_record_writes_the_pre_registered_fields(tmp_path):
    path = bakeoff.record("demo", {"winner": "x", "candidates": []}, rule="lowest WIS", split="2025", out_dir=tmp_path)
    data = json.loads(path.read_text())
    assert path.name == "bakeoff_demo.json"
    assert {"component", "rule", "split", "winner", "candidates", "git_hash", "timestamp"} <= set(data)


def test_unknown_component_is_a_clear_error():
    with pytest.raises(SystemExit):
        bakeoff.main(["no_such_component"])
