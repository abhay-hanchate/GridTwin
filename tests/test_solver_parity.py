import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.reference import pandapower_day
from engine.solver import DaySolver
from engine.types import Controls

DATE = "2019-05-15"


@pytest.fixture(scope="module")
def inputs():
    return day_inputs(DATE)


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(inputs, network):
    return scenarios_from_legacy(inputs, network)


@pytest.mark.parametrize("tap", [0, 1])
def test_symmetric_engine_matches_pandapower(network, scn, inputs, tap):
    """Gate G1: the production engine agrees with the independent reference on the 99-home street."""
    res = DaySolver(network, asymmetric=False).solve(scn, Controls(tap_pos=tap))
    u_ref, trafo_ref = pandapower_day(inputs, tap)
    assert np.abs(res.u_pu[0, :, :, 0] - u_ref).max() < 2e-4            # 0.05 V
    assert np.abs(res.trafo_loading_pct[0] - trafo_ref).max() < 0.2
    assert res.converged.all()
