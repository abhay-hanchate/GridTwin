import warnings

import numpy as np
import pandas as pd
import pytest

from engine import config
from engine.scenario_gen import ANOMALIES, Z10, AnalogPool, ScenarioGenerator, day_table, fit_copula, quantile_path
from engine.upstream import UpstreamModel

warnings.filterwarnings("ignore")
SLOTS = 96


def _forecast(scale=1.0):
    x = np.clip(np.sin((np.arange(SLOTS) - 24) / 48 * np.pi), 0, None)
    return pd.DataFrame({"p10": 0.6 * x * scale, "p50": 0.8 * x * scale, "p90": 1.0 * x * scale}, index=pd.date_range("2025-05-15", periods=SLOTS, freq="15min"))


def _loads(days=70, meters=8, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-05-01", periods=days * SLOTS, freq="15min")
    base = 0.5 + 0.4 * np.sin(2 * np.pi * (idx.hour + idx.minute / 60) / 24) ** 2
    return pd.DataFrame(base.to_numpy()[:, None] * rng.uniform(0.6, 1.4, meters)[None, :] * rng.uniform(0.9, 1.1, (len(idx), meters)), index=idx)


@pytest.fixture(scope="module")
def generator():
    loads = _loads()
    up = pd.Series(1.04 + 0.01 * np.sin(np.arange(len(loads)) / 400) + np.random.default_rng(1).normal(0, 0.003, len(loads)), index=loads.index)
    corr = np.array([[1, 0.0, -0.5], [0.0, 1, -0.4], [-0.5, -0.4, 1]])
    return ScenarioGenerator(corr, UpstreamModel.fit(up), AnalogPool.build(loads))


def test_quantile_path_hits_the_forecast_quantiles_and_never_goes_negative():
    fc = _forecast()
    mid = fc.p50.to_numpy()
    out = quantile_path(fc, np.array([0.0, Z10, -Z10, 3.0, -9.0]))
    assert np.allclose(out[0], fc.p50) and np.allclose(out[1], fc.p90) and np.allclose(out[2], fc.p10)
    assert (out[3] >= out[1]).all() and (out[4] >= 0).all() and out[4].max() < mid.max()
    assert quantile_path(fc, np.zeros((2, SLOTS))).shape == (2, SLOTS)


def test_fitted_copula_recovers_the_correlation_of_day_level_anomalies():
    rng = np.random.default_rng(0)
    true = np.array([[1, 0.1, -0.5], [0.1, 1, -0.3], [-0.5, -0.3, 1]])
    z = rng.multivariate_normal(np.zeros(3), true, 1500)
    table = pd.DataFrame(np.exp(z * 0.1), columns=list(ANOMALIES), index=pd.date_range("2020-01-01", periods=1500))
    assert np.abs(fit_copula(table) - true).max() < 0.08
    with pytest.raises(ValueError, match="at least 60 days"):
        fit_copula(table.iloc[:30])


def test_day_table_has_one_row_per_usable_day_and_three_anomalies():
    loads = _loads(days=70)
    pv = pd.Series(np.clip(np.sin((loads.index.hour - 6) / 12 * np.pi), 0, None), index=loads.index)
    pv = pv * np.repeat(np.random.default_rng(2).uniform(0.5, 1.0, 70), SLOTS)
    up = pd.Series(1.03 + np.random.default_rng(3).normal(0, 0.01, len(loads)), index=loads.index)
    table = day_table(loads, pv, up)
    assert list(table.columns) == list(ANOMALIES) and 55 <= len(table) <= 70
    assert abs(table.demand_index.mean() - 1) < 0.05 and abs(table.upstream_offset.mean()) < 0.01


def test_analog_pool_falls_back_to_the_nearest_month_and_is_reproducible():
    pool = AnalogPool.build(_loads())
    a = pool.home_ratios("2019-05-15", 4, 10, np.random.default_rng(5))
    b = pool.home_ratios("2019-05-15", 4, 10, np.random.default_rng(5))
    assert a.shape == (4, SLOTS, 10) and np.array_equal(a, b) and a.min() >= 0 and a.max() <= 8
    assert pool.home_ratios("2025-09-15", 1, 3, np.random.default_rng(0)).shape == (1, SLOTS, 3)   # only May-June data exist


def test_scenarios_have_the_right_shapes_and_respect_the_forecast(generator):
    scn = generator.sample("2019-05-15", 400, _forecast(), _forecast(0.5), 1.04, 12, np.random.default_rng(7))
    assert scn.load_kw.shape == (400, SLOTS, 12) and scn.pv_per_kwp.shape == (400, SLOTS) and scn.upstream_pu.shape == (400, SLOTS)
    pv_noon = scn.pv_per_kwp[:, 48]
    fc = _forecast().iloc[48]
    assert abs(np.median(pv_noon) - fc.p50) < 0.08 * fc.p50 + 0.02
    lo, hi = np.quantile(pv_noon, [0.1, 0.9])
    assert lo < fc.p50 < hi and (scn.pv_per_kwp >= 0).all() and scn.pv_per_kwp[:, 0].max() == 0     # no sun at midnight
    assert scn.upstream_pu.min() >= 0.8 and scn.upstream_pu.max() <= 1.2 and len(scn.labels) == 400


def test_day_level_correlations_follow_the_copula(generator):
    scn = generator.sample("2019-05-15", 1500, _forecast(), _forecast(0.5), 1.04, 4, np.random.default_rng(11))
    sun, up = scn.pv_per_kwp.mean(axis=1), scn.upstream_pu.mean(axis=1)
    demand = scn.load_kw.mean(axis=(1, 2))
    assert np.corrcoef(sun, up)[0, 1] < -0.15           # copula says -0.5 (diluted by the intraday part)
    assert np.corrcoef(demand, up)[0, 1] < -0.15


def test_same_seed_same_scenarios_and_bad_input_is_rejected(generator):
    args = ("2019-05-15", 5, _forecast(), _forecast(0.5), 1.04, 6)
    a, b = generator.sample(*args, np.random.default_rng(3)), generator.sample(*args, np.random.default_rng(3))
    assert np.array_equal(a.pv_per_kwp, b.pv_per_kwp) and np.array_equal(a.load_kw, b.load_kw)
    with pytest.raises(ValueError, match="96 quarter-hour"):
        generator.sample("2019-05-15", 2, _forecast().iloc[:48], _forecast(), 1.04, 3, np.random.default_rng(0))
    with_temp = generator.sample(*args, np.random.default_rng(3), temperature_c=np.full(SLOTS, 38.0))
    assert with_temp.ambient_c.shape == (5, SLOTS) and with_temp.ambient_c[0, 0] == 38.0


def test_real_data_gives_the_physically_expected_signs():
    base = config.PROCESSED_DIR
    load = pd.read_parquet(base / "load_kw.parquet")
    pv = pd.read_parquet(base / "pv_kw_per_kwp.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / "upstream_vm_pu.parquet")["upstream_vm_pu"]
    corr = fit_copula(day_table(load, pv, up))
    assert corr.shape == (3, 3) and np.allclose(np.diag(corr), 1)
    assert corr[1, 2] < -0.1          # heavy-demand days have lower grid voltage (measured about -0.34 on Mathura 2019-2021)
