import numpy as np
import pandas as pd

from ml.forecast import PARAMS, demand_features
from ml.explain import normalize_gain, permutation_mae_increase


def _series(days: int = 10) -> tuple[pd.Series, pd.Series]:
    index = pd.date_range("2019-05-01", periods=days * 96, freq="15min")
    load = pd.Series(0.4 + 0.1 * np.sin(np.arange(len(index)) / 12), index=index)
    temperature = pd.Series(25 + np.arange(len(index)) / 100, index=index)
    return load, temperature


def test_demand_features_do_not_use_target_interval_temperature():
    load, temperature = _series()
    target = load.index[-1]
    before, _ = demand_features(load, temperature)

    changed = temperature.copy()
    changed.loc[target] = 999.0
    after, _ = demand_features(load, changed)

    pd.testing.assert_series_equal(before.loc[target], after.loc[target])


def test_demand_features_only_use_lagged_temperature():
    load, temperature = _series()
    target = load.index[-1]
    previous_day = target - pd.Timedelta(days=1)
    before, _ = demand_features(load, temperature)

    changed = temperature.copy()
    changed.loc[previous_day] += 10
    after, _ = demand_features(load, changed)

    assert after.loc[target, "temp_lag_1d"] == before.loc[target, "temp_lag_1d"] + 10
    assert after.loc[target, "temp_change_lagged"] == before.loc[target, "temp_change_lagged"] + 10


def test_lightgbm_training_is_seeded_and_deterministic():
    assert PARAMS["random_state"] == 42
    assert PARAMS["deterministic"] is True
    assert PARAMS["force_col_wise"] is True


def test_gain_importance_is_normalized():
    result = normalize_gain(np.array([2.0, 3.0, 5.0]))
    assert np.isclose(result.sum(), 1.0)
    assert np.allclose(result, [0.2, 0.3, 0.5])


def test_permutation_importance_finds_the_predictive_feature():
    index = pd.date_range("2025-01-01", periods=200, freq="h")
    X = pd.DataFrame({"signal": np.arange(200), "noise": 1.0}, index=index)
    y = X["signal"] * 2

    importance = permutation_mae_increase(
        lambda frame: frame["signal"].to_numpy() * 2,
        X,
        y,
        repeats=3,
    )

    assert importance["signal"] > 0
    assert importance["noise"] == 0
