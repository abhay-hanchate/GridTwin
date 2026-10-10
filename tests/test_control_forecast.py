"""control.forecast: simulated observations and a causal forecast correction (no future data, no solar at night)."""
import numpy as np
import pytest

from backend.v2 import compute
from control.forecast import Corrector, Perturbation, make_world


@pytest.fixture(scope="module")
def world():
    net = compute.network("benchmark_250")
    return make_world("2025-05-15", net, n=20, perturbations=(Perturbation("pv_scale", 44, 52, 0.5, "cloud"),))


def test_observation_is_a_held_out_scenario_with_declared_perturbations(world):
    assert world.truth_index not in world.retained
    assert world.provenance == "simulated_observation"
    raw = world.all.pv_per_kwp[world.truth_index]
    assert world.observed.pv_per_kwp[0, 46] == pytest.approx(0.5 * raw[46])
    assert world.observed.pv_per_kwp[0, 30] == pytest.approx(raw[30])
    assert world.forecast.shape == (3, 96)


def test_horizon_uses_the_observation_now_and_never_a_future_one(world):
    corr = Corrector(world.forecast, rho=0.5, decay=0.9)
    for k in range(40):
        corr.observe(k, world.observed.take([k]))
    h = corr.horizon(40, 16, world.observed.take([40]))
    assert h.shape == (3, 16)
    assert h.pv_per_kwp[:, 0] == pytest.approx(np.full(3, world.observed.pv_per_kwp[0, 40]))   # now: observed
    # changing every future observation cannot change the horizon built at step 40
    other = world.observed.take(list(range(96)))
    other.pv_per_kwp[:, 41:] = 99.0
    h2 = corr.horizon(40, 16, other.take([40]))
    assert np.array_equal(h.pv_per_kwp, h2.pv_per_kwp) and np.array_equal(h.load_kw, h2.load_kw)


def test_a_cloud_lowers_the_corrected_solar_forecast_and_night_stays_dark(world):
    corr = Corrector(world.forecast, rho=0.5, decay=0.9)
    for k in range(48):
        corr.observe(k, world.observed.take([k]))
    h = corr.horizon(48, 16, world.observed.take([48]))
    plain = world.forecast.pv_per_kwp[:, 49:64]
    assert (h.pv_per_kwp[:, 1:] <= plain + 1e-12).all() and (h.pv_per_kwp[:, 1:] < plain - 1e-6).any()
    night = Corrector(world.forecast, rho=0.5, decay=0.9)
    for k in range(48):
        night.observe(k, world.observed.take([k]))
    late = night.horizon(80, 16, world.observed.take([80]))
    assert (late.pv_per_kwp[:, world.forecast.pv_per_kwp[0, 80:96] == 0] == 0).all()
