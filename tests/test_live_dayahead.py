from datetime import date

import numpy as np
import pandas as pd
import pytest

from ml import live_dayahead as lda


def _data(months: int = 10, seed: int = 0) -> pd.DataFrame:
    """Synthetic long table: two districts, 15-minute rows, demand driven by slot, season and the UP anchor."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-05-01", periods=months * 30 * 96, freq="15min")
    day = pd.Series(idx.normalize(), index=idx)
    ratio_by_day = pd.Series(rng.normal(1.0, 0.05, day.nunique()), index=day.unique())
    frames = []
    for d, name in enumerate(lda.DISTRICT_IDS):
        ratio = ratio_by_day.reindex(day).to_numpy()
        shape = 0.4 + 0.3 * np.sin((idx.hour + idx.minute / 60) / 24 * 2 * np.pi) ** 2
        temp = 25 + 10 * np.sin((idx.dayofyear - 100) / 365 * 2 * np.pi)
        demand = shape * (1 + 4 * (ratio - 1)) * (1 + 0.01 * (temp - 25)) + rng.normal(0, 0.03, len(idx))
        voltage = 245 - 40 * (ratio - 1) + rng.normal(0, 2, len(idx))
        frames.append(pd.DataFrame({"ts": idx, "district": name, "demand": demand, "voltage": voltage, "temp": temp,
                                    "up_ratio": ratio}))
    return lda.add_features(pd.concat(frames, ignore_index=True), holidays_set=set())


def test_features_hold_no_household_lags_and_the_live_set_adds_only_the_anchor():
    data = _data(2)
    assert set(lda.FEATURES_LIVE) - set(lda.FEATURES_PATTERN) == {"up_ratio"}
    for f in lda.FEATURES_LIVE:
        assert "lag" not in f and f not in ("demand", "voltage")
        assert f in data.columns


def test_holiday_flags_use_the_calendar(tmp_path):
    frame = pd.DataFrame({"ts": pd.date_range("2019-10-27", periods=192, freq="15min"), "district": "mathura",
                          "temp": 25.0, "up_ratio": 1.0})
    out = lda.add_features(frame, holidays_set={date(2019, 10, 27)})
    assert out["is_holiday"].iloc[0] == 1 and out["is_holiday"].iloc[-1] == 0
    assert out["is_holiday_prev"].iloc[-1] == 1


def test_climatology_gives_ordered_group_quantiles():
    data = _data(4)
    train, test = data[data.ts < "2019-08-01"], data[data.ts >= "2019-08-01"]
    pred = lda.climatology(train, test, "demand")
    assert len(pred) == len(test)
    assert (pred["p10"] <= pred["p50"]).all() and (pred["p50"] <= pred["p90"]).all()


def test_walk_forward_never_sees_the_month_it_predicts():
    data = _data(9)
    a = lda.walk_forward(data, "demand", lda.FEATURES_LIVE, start_after_months=6, n_estimators=40)
    changed = data.copy()
    month = a["month"].max()
    in_month = changed.ts.dt.to_period("M").astype(str) == month
    changed.loc[in_month, "demand"] += 5.0                                # the future is very different
    b = lda.walk_forward(changed, "demand", lda.FEATURES_LIVE, start_after_months=6, n_estimators=40)
    pd.testing.assert_frame_equal(a[a.month == month][["p10", "p50", "p90"]], b[b.month == month][["p10", "p50", "p90"]])


def test_mondrian_widening_uses_earlier_months_of_the_same_season_only():
    idx = pd.RangeIndex(4000)
    months = np.repeat(["2019-12", "2020-01", "2020-06", "2020-12"], 1000)
    raw = pd.DataFrame({"p10": 0.0, "p50": 0.5, "p90": 1.0, "month": months}, index=idx)
    raw["season"] = lda.season_of(pd.PeriodIndex(raw["month"], freq="M").month)
    y = pd.Series(np.r_[np.full(2000, 1.5), np.full(1000, 0.5), np.full(1000, 0.5)], index=idx)  # winters miss high
    out = lda.mondrian_widen(raw, y, min_points=500)
    dec20 = out[out.month == "2020-12"]
    assert dec20["p90"].iloc[0] == pytest.approx(1.5, abs=1e-9)           # learnt from the two earlier winter months
    jun = out[out.month == "2020-06"]
    assert jun["p90"].iloc[0] == pytest.approx(1.5, abs=1e-9)            # no summer history yet: all earlier months
    first = out[out.month == "2019-12"]
    assert (first["p90"] == 1.0).all()                                    # nothing earlier: left unwidened
    pools = out.groupby("month")["cal_pool"].first().to_dict()
    assert pools == {"2019-12": "none", "2020-01": "season", "2020-06": "all", "2020-12": "season"}


def test_live_forecast_falls_back_to_pattern_only_without_the_anchor(tmp_path):
    data = _data(8)
    lda.train_final(data, model_dir=tmp_path, n_estimators=40)
    temps = pd.Series(28.0, index=pd.date_range("2019-12-15", periods=96, freq="15min"))
    with_anchor = lda.live_forecast("mathura", date(2019, 12, 15), temperature=temps, ratio=1.03, model_dir=tmp_path,
                                    holidays_set=set())
    without = lda.live_forecast("mathura", date(2019, 12, 15), temperature=temps, ratio=float("nan"),
                                model_dir=tmp_path, holidays_set=set())
    for out in (with_anchor, without):
        for target in ("demand", "voltage"):
            pts = out[target]["points"]
            assert len(pts) == 96 and all(p["p10"] <= p["p50"] <= p["p90"] for p in pts)
    assert with_anchor["anchor"]["used"] is True and without["anchor"]["used"] is False
    assert "pattern" in without["anchor"]["note"]


def test_decision_rule_follows_the_pre_registration():
    ok = {"mae": 0.90, "coverage": 0.80, "by_season": {"winter": 0.79, "summer": 0.81}}
    rows = {"climatology": {"mae": 1.10, "coverage": 0.80, "by_season": {"winter": 0.8, "summer": 0.8}},
            "pattern_only": {"mae": 0.95, "coverage": 0.80, "by_season": {"winter": 0.8, "summer": 0.8}},
            "live_anchored": ok}
    assert lda.decide(rows)["adopted"] == "live_anchored"
    rows["live_anchored"] = {**ok, "mae": 1.05}                          # less than 10% better than climatology
    assert lda.decide(rows)["adopted"] != "live_anchored"
    rows["live_anchored"] = {**ok, "by_season": {"winter": 0.65, "summer": 0.81}}     # a season outside 70-90%
    assert lda.decide(rows)["adopted"] != "live_anchored"
