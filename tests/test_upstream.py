import numpy as np
import pandas as pd
import pytest

from engine.upstream import (CANDIDATES, AnalogDays, AR1Shape, Climatology, LgbmDayQuantiles, crps_samples, day_table,
                             decide, evaluate, previous_day_means)

SLOTS = 96


def _series(days=300, phi=0.6, sigma=0.01, seed=0, start="2020-01-01"):
    """Known structure: monthly level + AR(1) day deviation (phi) + a fixed daily shape + small slot noise."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * SLOTS, freq="15min")
    dev, means = 0.0, []
    for d in range(days):
        dev = phi * dev + rng.normal(0, sigma)
        month = (pd.Timestamp(start) + pd.Timedelta(days=d)).month
        means.append(1.03 + 0.01 * np.sin(2 * np.pi * month / 12) + dev)
    shape = 0.01 * np.sin(2 * np.pi * np.arange(SLOTS) / SLOTS)
    v = np.concatenate([m + shape + rng.normal(0, 0.002, SLOTS) for m in means])
    return pd.Series(v, index=idx)


@pytest.fixture(scope="module")
def train():
    return _series(seed=0)


@pytest.fixture(scope="module")
def fitted(train):
    return {name: cls.fit(train) for name, cls in CANDIDATES.items()}


def test_day_table_drops_short_days_and_fills_small_gaps():
    s = _series(days=5)
    s.iloc[10:15] = np.nan                       # 5 missing slots on day 1: kept and filled
    s.iloc[SLOTS * 2: SLOTS * 2 + 30] = np.nan    # 30 missing on day 3: dropped
    table = day_table(s)
    assert len(table) == 4 and np.isfinite(table.to_numpy()).all()
    prev = previous_day_means(table)
    assert prev.isna().tolist() == [True, False, True, False]   # day 4 follows the dropped day 3


@pytest.mark.parametrize("name", list(CANDIDATES))
def test_every_candidate_gives_reproducible_clipped_paths(fitted, name):
    m = fitted[name]
    a = m.sample("2020-09-01", 40, 1.04, np.random.default_rng(3))
    b = m.sample("2020-09-01", 40, 1.04, np.random.default_rng(3))
    assert a.shape == (40, SLOTS) and np.array_equal(a, b)
    assert (a >= 0.8).all() and (a <= 1.2).all()


@pytest.mark.parametrize("name", list(CANDIDATES))
def test_day_z_orders_the_day_level(fitted, name):
    paths = fitted[name].sample("2020-06-15", 3, 1.04, np.random.default_rng(0), day_z=np.array([-2.0, 0.0, 2.0]))
    means = paths.mean(axis=1)
    assert means[0] < means[1] < means[2]


@pytest.mark.parametrize("name", ["analog_days", "ar1_shape", "lgbm_day_quantiles"])
def test_a_high_previous_day_raises_the_forecast(fitted, name):
    low = fitted[name].sample("2020-09-01", 300, 1.01, np.random.default_rng(0)).mean()
    high = fitted[name].sample("2020-09-01", 300, 1.06, np.random.default_rng(0)).mean()
    assert high > low + 0.005


def test_climatology_ignores_the_previous_day(fitted):
    a = fitted["climatology"].sample("2020-09-01", 50, 1.01, np.random.default_rng(1))
    b = fitted["climatology"].sample("2020-09-01", 50, 1.06, np.random.default_rng(1))
    assert np.array_equal(a, b)


def test_ar1_fit_recovers_the_day_to_day_persistence(fitted):
    m = fitted["ar1_shape"]
    assert 0.4 < m.phi < 0.8 and 0.007 < m.sigma_day < 0.014


def test_crps_of_samples():
    assert crps_samples(np.array([1.0, 1.0, 1.0]), 1.0) == 0.0
    assert crps_samples(np.array([2.0]), 1.0) == pytest.approx(1.0)
    x = np.random.default_rng(0).normal(0, 1, 20000)                # CRPS of N(0,1) at 0 is 0.2337
    assert crps_samples(x, 0.0) == pytest.approx(0.2337, abs=0.01)


def test_evaluate_scores_the_model_that_matches_the_data_well(train):
    test = _series(seed=1, start="2021-01-01", days=200)
    rep = evaluate(AR1Shape.fit(train), test, n=200)
    assert rep["days"] > 150 and 0.65 <= rep["day_max_coverage_80"] <= 0.95
    assert rep["crps_day_max"] > 0 and 0 < rep["slot_coverage_80"] <= 1
    clim = evaluate(Climatology.fit(train), test, n=200)
    assert rep["crps_day_mean"] < clim["crps_day_mean"]           # yesterday carries information here


def test_lgbm_uses_the_full_previous_day_in_evaluation(train):
    model = LgbmDayQuantiles.fit(train)
    rep = evaluate(model, _series(seed=2, start="2021-01-01", days=60), n=50)
    assert rep["days"] > 40


def test_analog_pool_is_limited_to_k_days(train):
    m = AnalogDays.fit(train, k=5)
    paths = m.sample("2020-06-15", 500, 1.04, np.random.default_rng(0))
    assert len({tuple(np.round(p[:3], 6)) for p in paths}) <= 5


def _row(name, *covs_crps):
    return {"name": name, "protocols": {f"p{i}": {"day_max_coverage_80": c, "crps_day_max": r}
                                        for i, (c, r) in enumerate(covs_crps)}}


def test_decide_rule_band_tie_and_miss():
    rows = [_row("simple", (0.80, 0.0102), (0.75, 0.0100)), _row("complex", (0.81, 0.0100), (0.79, 0.0100)),
            _row("out", (0.95, 0.0050), (0.80, 0.0050))]
    d = decide(rows)
    assert d["in_band"] == ["simple", "complex"] and d["winner"] == "simple"      # within 2%: simplest wins
    rows[0]["protocols"]["p0"]["crps_day_max"] = 0.0110                          # now clearly worse
    assert decide(rows)["winner"] == "complex"
    miss = decide([_row("a", (0.60, 0.01), (0.95, 0.01)), _row("b", (0.68, 0.01), (0.92, 0.01))])
    assert miss["winner"] == "b" and miss["in_band"] == [] and "miss" in miss["reason"]
