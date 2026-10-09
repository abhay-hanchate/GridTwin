import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.fixes import catalog, switching
from engine.fixes.battery import solve_with_battery, with_battery
from engine.fixes.envelopes import compute_envelope
from engine.fixes.phase_assign import plan_phases
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls
from engine.violations import evaluate

warnings.filterwarnings("ignore")
RULE = get_rule("pm10")


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="random")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


def test_phase_plan_balances_a_lopsided_street_and_respects_limits():
    net_kw = np.random.default_rng(0).uniform(-0.5, 1.5, size=(8, 12))        # 8 steps, 12 homes
    current = np.zeros(12, dtype=int)                                          # everyone on phase A
    plan = plan_phases(net_kw, current, time_limit_s=5)
    assert plan.status in {"OPTIMAL", "FEASIBLE"} and plan.imbalance_after_kw < 0.3 * plan.imbalance_before_kw
    assert len(set(plan.phases.tolist())) == 3

    movable = np.arange(12) < 6
    pinned = plan_phases(net_kw, current, movable=movable, time_limit_s=5)
    assert (pinned.phases[~movable] == 0).all()

    capped = plan_phases(net_kw, current, max_moves=3, time_limit_s=5)
    assert capped.moved <= 3


def test_phase_plan_is_reproducible():
    net_kw = np.random.default_rng(1).uniform(-0.5, 1.5, size=(8, 12))
    a = plan_phases(net_kw, np.zeros(12, dtype=int), time_limit_s=5)
    b = plan_phases(net_kw, np.zeros(12, dtype=int), time_limit_s=5)
    assert (a.phases == b.phases).all()


def test_envelope_reduces_unsafe_steps_and_curtails_less_than_uniform(network, scn):
    solver = DaySolver(network)
    before = evaluate(solver.solve(scn), RULE).unsafe.sum()
    env = compute_envelope(solver, scn, RULE)
    assert env.limit_kw.shape == (96, network.n_homes) and (env.limit_kw >= 0).all()
    after = evaluate(solver.solve(scn, Controls(export_limit_kw=env.limit_kw)), RULE).unsafe.sum()
    assert after < before
    assert env.curtailed_kwh < 500                       # uniform curtailment needs about 880 kWh for the same day


def test_battery_lowers_the_peak_and_respects_its_state_of_charge(network, scn):
    base = DaySolver(network).solve(scn)
    spec = BatterySpec(kw=100.0, kwh=400.0, node=catalog.worst_node(network, scn))
    res = solve_with_battery(network, scn, spec, RULE)
    assert np.nanmax(res.u_pu) < np.nanmax(base.u_pu)
    assert 0 < res.battery_kw.max() <= spec.kw + 1e-6
    power = res.battery_kw[0]
    soc = spec.soc_start + np.cumsum(np.where(power > 0, power * spec.efficiency, power / spec.efficiency) * 0.25 / spec.kwh)
    assert soc.min() >= spec.soc_min - 1e-6 and soc.max() <= spec.soc_max + 1e-6
    assert with_battery(network, spec).n_homes == network.n_homes + 3


def test_every_switching_candidate_stays_radial(network):
    assert network.is_radial()
    cands = switching.candidates(network)
    assert cands, "the benchmark street has feeder ends close enough to tie"
    for rec in cands[:12]:
        net_s = switching.apply(network, rec)
        assert net_s.n_lines == network.n_lines and net_s.is_radial()


def test_a_loop_is_detected():
    n = from_pandapower(build_grid(0.0))
    loop = n.with_topology(add=[{"from": int(n.line_from[0]), "to": int(n.line_to[-1]), "r1": 0.1, "x1": 0.03, "r0": 0.3,
                                 "x0": 0.09, "c1": 0.0, "i_n": 200.0, "length_m": 50.0}])
    assert not loop.is_radial()


def test_equal_cost_fixes_are_separated_by_voltage_margin_before_loss():
    from engine.fixes.base import cost_vector
    narrow = {"curtailed_kwh": 0.0, "battery_throughput_kwh": 0.0, "losses_kwh": 1.0, "max_vm_pu": 1.050, "min_vm_pu": 0.905}
    wide = {"curtailed_kwh": 0.0, "battery_throughput_kwh": 0.0, "losses_kwh": 2.0, "max_vm_pu": 1.080, "min_vm_pu": 0.950}
    assert cost_vector(wide, 0, RULE) < cost_vector(narrow, 0, RULE)          # wide margin wins despite higher loss
    assert cost_vector(wide, 0, RULE) < cost_vector({**wide, "curtailed_kwh": 5.0}, 0, RULE)   # solar wasted still dominates
