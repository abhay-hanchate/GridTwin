import time

import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.solver import DaySolver


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


@pytest.mark.perf
def test_day_replay_speed_budgets(network, scn):
    sym_solver, asym_solver = DaySolver(network, asymmetric=False), DaySolver(network, asymmetric=True)
    sym_solver.solve(scn); asym_solver.solve(scn)                         # warm up
    t0 = time.perf_counter(); sym_solver.solve(scn); t_sym = time.perf_counter() - t0
    t0 = time.perf_counter(); asym_solver.solve(scn); t_asym = time.perf_counter() - t0
    assert t_sym < 0.1 and t_asym < 0.3, (t_sym, t_asym)
