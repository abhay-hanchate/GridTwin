import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.risk import assess_risk, longest_run
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.verdict import binding_limit_arrays, shortfall
from engine.violations import evaluate

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


def _spread(scn, solar_scales, upstream_shifts):
    n = len(solar_scales)
    return DayScenarioBatch(scn.t, np.repeat(scn.load_kw, n, axis=0), scn.pv_per_kwp * np.array(solar_scales)[:, None],
                            scn.upstream_pu + np.array(upstream_shifts)[:, None], scn.load_pf, tuple(map(str, range(n))))


def test_longest_run():
    flags = np.array([[0, 1, 1, 0, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0]], dtype=bool)
    assert longest_run(flags).tolist() == [3, 0]


def test_risk_rises_with_solar_and_names_the_hours(network, scn):
    rule = get_rule("pm10")
    solver = DaySolver(network, asymmetric=True)
    sunny = assess_risk(solver, _spread(scn, [1.0] * 30, [0.0] * 30), Controls(), rule)
    dull = assess_risk(solver, _spread(scn, [0.3] * 30, [0.0] * 30), Controls(), rule)
    assert 0.0 <= dull.p_unsafe.min() and sunny.p_unsafe.max() <= 1.0
    assert sunny.expected_unsafe_hours > dull.expected_unsafe_hours
    assert sunny.level == "act" and sunny.first_act is not None
    assert set(sunny.window_risk) == {"15 min", "1 h", "3 h", "24 h"}
    assert sunny.window_risk["15 min"] >= sunny.window_risk["3 h"]


def test_risk_has_spread_when_the_scenarios_differ(network, scn):
    rule = get_rule("pm10")
    solver = DaySolver(network, asymmetric=True)
    mixed = assess_risk(solver, _spread(scn, np.linspace(0.3, 1.1, 40), np.linspace(-0.03, 0.03, 40)), Controls(), rule)
    assert 0 < mixed.p_unsafe.max() < 1 and mixed.unsafe_hours_p10 < mixed.unsafe_hours_p90
    assert mixed.peak_voltage_v["p10"] < mixed.peak_voltage_v["p90"]


def test_binding_limit_from_arrays_matches_the_legacy_wording(network, scn):
    res = DaySolver(network, asymmetric=False).solve(scn)
    rule = get_rule("pm10")
    limit = binding_limit_arrays(evaluate(res, rule), res, rule)
    assert limit["type"] == "overvoltage" and limit["steps"] == 26
    assert limit["worst"]["value"] * 230 == pytest.approx(263.1, abs=0.3) and limit["worst"]["limit"] == 1.10


def test_shortfall_words(network):
    over = {"type": "overvoltage", "steps": 3, "worst": {"value": 1.0777, "limit": 1.06}}
    assert "tap step" in shortfall(over, get_rule("up_2005"), network)
    trafo = {"type": "trafo_overload", "steps": 2, "worst": {"value": 172.0, "limit": 100.0}}
    assert "450 kVA" in shortfall(trafo, get_rule("pm10"), network)          # 1.72 x 250 kVA = 430, rounded up to 25
