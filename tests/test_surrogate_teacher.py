"""The surrogate's teacher: arrays of operating states solved by the real solver, matching the engine's own paths."""
import warnings

import numpy as np
import pytest

from backend.v2 import compute
from engine.fixes.battery import with_battery
from engine.inverters import VoltVarCurve
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch
from ml.surrogate import schema
from ml.surrogate.teacher import StateArrays, solve_states

warnings.filterwarnings("ignore")
STREET = "rural_weak_63"


@pytest.fixture(scope="module")
def net():
    return compute.network(STREET)


@pytest.fixture(scope="module")
def scn(net):
    return compute.scenarios("2025-05-15", net, n=2)


def _states(net, scn, steps, *, keep=1.0, battery=0.0, tap=0, mode="fixed_pf"):
    load = scn.load_kw[0, steps]
    pv = scn.pv_per_kwp[0, steps, None] * net.house_kwp[None, :] * keep
    b = len(steps)
    return StateArrays(load_kw=load, pv_kw=pv, pv_kwp=np.tile(net.house_kwp, (b, 1)), upstream_pu=scn.upstream_pu[0, steps],
                       battery_kw=np.full(b, battery), tap_pos=np.full(b, tap),
                       mode=np.full(b, schema.MODES.index(mode)))


def test_fixed_power_factor_with_curtailment_matches_the_day_solver(net, scn):
    steps = np.arange(40, 56)
    out = solve_states(net, _states(net, scn, steps, keep=0.8, tap=1), battery_node=schema.battery_node(STREET))
    one = DayScenarioBatch(scn.t[steps], scn.load_kw[:1, steps], scn.pv_per_kwp[:1, steps], scn.upstream_pu[:1, steps])
    ref = DaySolver(net).solve(one, Controls(tap_pos=1, curtail_keep=0.8))
    np.testing.assert_allclose(out.u_pu, ref.u_pu[0], atol=1e-6)
    np.testing.assert_allclose(out.line_loading_pct, ref.line_loading_pct[0], atol=1e-4)
    np.testing.assert_allclose(out.trafo_loading_pct, ref.trafo_loading_pct[0], atol=1e-4)
    assert out.converged.all()


def test_volt_var_matches_the_day_solver_within_its_tolerance(net, scn):
    steps = np.arange(44, 52)
    out = solve_states(net, _states(net, scn, steps, mode="volt_var"), battery_node=schema.battery_node(STREET))
    one = DayScenarioBatch(scn.t[steps], scn.load_kw[:1, steps], scn.pv_per_kwp[:1, steps], scn.upstream_pu[:1, steps])
    ref = DaySolver(net).solve(one, Controls(volt_var=VoltVarCurve()))
    np.testing.assert_allclose(out.u_pu, ref.u_pu[0], atol=2e-4)


def test_battery_is_three_unity_power_factor_pseudo_homes(net, scn):
    steps = np.arange(80, 84)
    node = schema.battery_node(STREET)
    out = solve_states(net, _states(net, scn, steps, battery=30.0), battery_node=node)
    spec = BatterySpec(kw=30.0, kwh=60.0, node=node)
    load = np.concatenate([scn.load_kw[:1, steps], np.full((1, len(steps), 3), 10.0)], axis=2)
    pf = np.r_[np.full(net.n_homes, 0.95), np.ones(3)]
    ref = DaySolver(with_battery(net, spec)).solve(
        DayScenarioBatch(scn.t[steps], load, scn.pv_per_kwp[:1, steps], scn.upstream_pu[:1, steps], pf))
    np.testing.assert_allclose(out.u_pu, ref.u_pu[0], atol=1e-6)
    idle = solve_states(net, _states(net, scn, steps), battery_node=node)
    assert np.nanmin(out.u_pu) < np.nanmin(idle.u_pu)                # charging at night pulls the voltage down


def test_mixed_settings_in_one_call_are_solved_group_by_group(net, scn):
    a = _states(net, scn, np.arange(40, 44), tap=0)
    b = _states(net, scn, np.arange(40, 44), tap=2, mode="volt_watt")
    both = StateArrays.concat([a, b])
    out = solve_states(net, both, battery_node=schema.battery_node(STREET))
    alone = solve_states(net, b, battery_node=schema.battery_node(STREET))
    np.testing.assert_allclose(out.u_pu[4:], alone.u_pu, atol=1e-6)
    assert out.u_pu.shape == (8, len(net.lv_nodes), 3)
