import numpy as np
import pytest

from engine.reliability import Climatology, brier, reliability_table


def test_reliability_table_bins_and_frequencies():
    pred = np.array([0.05, 0.1, 0.5, 0.55, 0.95])
    obs = np.array([0, 0, 1, 0, 1], dtype=bool)
    rows = {r["bin"]: r for r in reliability_table(pred, obs)}
    assert rows["0.0-0.2"]["n"] == 2 and rows["0.0-0.2"]["observed_frequency"] == 0.0
    assert rows["0.4-0.6"]["n"] == 2 and rows["0.4-0.6"]["observed_frequency"] == 0.5
    assert rows["0.8-1.0"]["n"] == 1 and rows["0.2-0.4"]["mean_predicted"] is None


def test_brier_score():
    assert brier(np.array([1.0, 0.0]), np.array([True, False])) == 0.0
    assert brier(np.array([0.5, 0.5]), np.array([True, False])) == pytest.approx(0.25)


def test_weather_class_uses_the_thresholds():
    assert [Climatology.weather_class(x, (0.4, 0.8)) for x in (0.1, 0.5, 0.9)] == ["cloudy", "mixed", "sunny"]
