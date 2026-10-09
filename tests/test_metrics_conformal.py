import numpy as np
import pandas as pd
import pytest

from ml.conformal import apply_conformal, conformal_q
from ml.metrics import coverage, pinball, skill, wis


def test_wis_for_a_point_inside_the_interval():
    # IS = 2 (width), |y - median| = 0  ->  (0.5*0 + 0.1*2) / 1.5
    assert wis(np.array([5.0]), np.array([4.0]), np.array([5.0]), np.array([6.0])) == pytest.approx(0.2 / 1.5)


def test_wis_penalises_a_miss():
    # y=8, interval 4..6, median 5: IS = 2 + 10*(8-6) = 22; (0.5*3 + 0.1*22) / 1.5
    assert wis(np.array([8.0]), np.array([4.0]), np.array([5.0]), np.array([6.0])) == pytest.approx(3.7 / 1.5)


def test_pinball_is_zero_for_a_perfect_forecast():
    y = np.array([1.0, 2.0, 3.0])
    assert pinball(y, {0.1: y, 0.5: y, 0.9: y}) == 0.0


def test_coverage_and_skill():
    assert coverage(np.array([1, 2, 3, 4]), np.array([0, 0, 0, 0]), np.array([2, 2, 2, 2])) == 0.5
    assert skill(0.9, 1.0) == pytest.approx(0.1)


def test_conformal_widening_reaches_the_target_coverage():
    rng = np.random.default_rng(1)
    y = pd.Series(rng.normal(0, 1, 12000))                                           # large enough that noise is about 0.8%
    pred = pd.DataFrame({"p10": -0.2, "p50": 0.0, "p90": 0.2}, index=y.index)        # far too narrow
    q = conformal_q(pred.iloc[:6000], y.iloc[:6000], alpha=0.2)
    adj = apply_conformal(pred.iloc[6000:], q)
    cov = ((y.iloc[6000:] >= adj["p10"]) & (y.iloc[6000:] <= adj["p90"])).mean()
    assert 0.77 <= cov <= 0.83


def test_apply_conformal_keeps_quantiles_ordered_and_respects_the_floor():
    pred = pd.DataFrame({"p10": [0.1], "p50": [0.2], "p90": [0.3]})
    adj = apply_conformal(pred, 0.5, floor=0.0)
    assert adj["p10"].iloc[0] == 0.0 and adj["p10"].iloc[0] <= adj["p50"].iloc[0] <= adj["p90"].iloc[0]
    shrunk = apply_conformal(pred, -0.5)
    assert shrunk["p10"].iloc[0] <= shrunk["p50"].iloc[0] <= shrunk["p90"].iloc[0]
