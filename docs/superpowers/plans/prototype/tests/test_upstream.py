import numpy as np
import pandas as pd
import pytest

from engine.upstream import UpstreamModel, evaluate


def _series(days=240, phi=0.6, sigma=0.01, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=days * 96, freq="15min")
    dev, means = 0.0, []
    for _ in range(days):
        dev = phi * dev + rng.normal(0, sigma)
        means.append(1.04 + dev)
    shape = 0.01 * np.sin(2 * np.pi * np.arange(96) / 96)
    v = np.concatenate([m + shape + rng.normal(0, 0.002, 96) for m in means])
    return pd.Series(v, index=idx)


def test_fit_recovers_the_day_to_day_persistence():
    model = UpstreamModel.fit(_series())
    assert 0.4 < model.phi < 0.8
    assert 0.007 < model.sigma_day < 0.014


def test_samples_have_the_right_shape_and_are_reproducible():
    model = UpstreamModel.fit(_series())
    a = model.sample(pd.Timestamp("2020-09-01"), 50, 1.04, np.random.default_rng(3))
    b = model.sample(pd.Timestamp("2020-09-01"), 50, 1.04, np.random.default_rng(3))
    assert a.shape == (50, 96) and np.array_equal(a, b)
    assert (a >= 0.8).all() and (a <= 1.2).all()


def test_a_high_previous_day_raises_the_forecast():
    model = UpstreamModel.fit(_series())
    low = model.sample(pd.Timestamp("2020-09-01"), 200, 1.02, np.random.default_rng(0)).mean()
    high = model.sample(pd.Timestamp("2020-09-01"), 200, 1.08, np.random.default_rng(0)).mean()
    assert high > low


def test_interval_for_the_daily_maximum_is_roughly_calibrated():
    train, test = _series(seed=0), _series(seed=1)
    rep = evaluate(UpstreamModel.fit(train), test, n=200)
    assert 0.65 <= rep["day_max_coverage_80"] <= 0.95 and rep["days"] > 100


def test_a_supplied_day_draw_moves_the_whole_day_and_is_reproducible():
    m = UpstreamModel.fit(_series())
    up = m.sample(pd.Timestamp("2021-06-15"), 3, 1.0, np.random.default_rng(0), day_z=np.array([-2.0, 0.0, 2.0]))
    means = up.mean(axis=1)
    assert means[0] < means[1] < means[2]
    again = m.sample(pd.Timestamp("2021-06-15"), 3, 1.0, np.random.default_rng(0), day_z=np.array([-2.0, 0.0, 2.0]))
    assert np.allclose(up, again)
