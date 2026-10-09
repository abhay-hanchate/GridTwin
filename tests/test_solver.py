import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.network import assign_phases, from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import evaluate, summarise

warnings.filterwarnings("ignore")
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


@pytest.fixture(scope="module")
def sym(network):
    return DaySolver(network, asymmetric=False)


def test_unsafe_step_count_matches_the_legacy_engine(sym, scn):
    res = sym.solve(scn)
    viol = evaluate(res, get_rule("pm10"))
    s = summarise(res, viol)
    assert s["violation_steps"] == 26 and s["solver_failed_steps"] == 0       # legacy S4: 26 steps = 6 h 30 min
    assert s["max_vm_pu"] * 230 == pytest.approx(263.1, abs=0.3)
    assert s["max_trafo_loading_pct"] == pytest.approx(44.5, abs=0.3)
    assert s["reverse_flow_steps"] > 0


def test_asymmetric_engine_equals_symmetric_when_every_home_is_split_over_three_phases(network, scn, sym):
    # Each home becomes three co-located homes with a third of the load and PV, one per phase.
    h = network.n_homes
    net3 = network.replace(house_node=np.repeat(network.house_node, 3), house_phase=np.tile([0, 1, 2], h),
                           house_kwp=np.repeat(network.house_kwp / 3, 3))
    scn3 = DayScenarioBatch(scn.t, np.repeat(scn.load_kw / 3, 3, axis=2), scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels)
    res3 = DaySolver(net3, asymmetric=True).solve(scn3)
    res = sym.solve(scn)
    for phase in range(3):
        assert np.abs(res3.u_pu[0, :, :, phase] - res.u_pu[0, :, :, 0]).max() < 5e-4
    assert res3.vuf_pct.max() < 0.05 and res3.neutral_a.max() < 1.0


def test_single_phase_homes_give_higher_voltage_and_unbalance_than_the_balanced_model(network, scn, sym):
    balanced = sym.solve(scn).u_pu.max()
    peaks = {}
    for mode in ("round_robin", "random", "all_a"):
        res = DaySolver(network.with_phases(assign_phases(network.n_homes, mode)), asymmetric=True).solve(scn)
        assert res.converged.all()
        peaks[mode] = (res.u_pu.max(), res.vuf_pct.max())
    assert peaks["round_robin"][0] > balanced
    assert peaks["round_robin"][0] < peaks["random"][0] < peaks["all_a"][0]
    assert peaks["round_robin"][1] < peaks["random"][1] < peaks["all_a"][1]


def test_standard_volt_var_clears_the_day_in_the_symmetric_engine(sym, scn):
    res = sym.solve(scn, Controls(volt_var=VoltVarCurve()))
    s = summarise(res, evaluate(res, get_rule("pm10")))
    assert s["violation_steps"] == 0
    assert s["max_vm_pu"] * 230 == pytest.approx(250.1, abs=0.5) and s["min_vm_pu"] * 230 == pytest.approx(220.5, abs=0.5)
    assert s["max_trafo_loading_pct"] == pytest.approx(66.4, abs=1.0)
    assert 3 <= res.passes <= 40


def test_volt_watt_curtails_and_curtail_keep_matches_legacy(sym, scn):
    vw = summarise(*(lambda r: (r, evaluate(r, get_rule("pm10"))))(sym.solve(scn, Controls(volt_watt=VoltWattCurve()))))
    assert vw["curtailed_kwh"] > 0
    keep = sym.solve(scn, Controls(curtail_keep=0.6))
    s = summarise(keep, evaluate(keep, get_rule("pm10")))
    assert s["curtailed_kwh"] == pytest.approx(489.3, abs=1.0)           # legacy export_cap_60
    assert s["violation_steps"] == 15                                     # legacy: 3 h 45 min


def test_export_limit_caps_net_export_per_home(sym, scn, network):
    limit = np.full(network.n_homes, 0.5)                                 # 0.5 kW export per home
    res = sym.solve(scn, Controls(export_limit_kw=limit))
    exported = res.pv_kw[0] - scn.load_kw[0].sum(axis=1)
    assert (exported <= 0.5 * network.n_homes + 1e-6).all()
    assert res.pv_kw.sum() < res.pv_avail_kw.sum()


def test_stacked_scenarios_equal_individual_runs(sym, scn):
    both = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw, scn.load_kw * 0.5]), np.concatenate([scn.pv_per_kwp] * 2),
                            np.concatenate([scn.upstream_pu] * 2), scn.load_pf, ("a", "b"))
    r2 = sym.solve(both)
    r_a, r_b = sym.solve(scn), sym.solve(DayScenarioBatch(scn.t, scn.load_kw * 0.5, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, ("b",)))
    assert np.allclose(r2.u_pu[0], r_a.u_pu[0], atol=1e-9) and np.allclose(r2.u_pu[1], r_b.u_pu[0], atol=1e-9)


def test_an_impossible_scenario_is_masked_not_hidden(sym, scn):
    bad = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw, scn.load_kw * 5000]), np.concatenate([scn.pv_per_kwp] * 2),
                           np.concatenate([scn.upstream_pu] * 2), scn.load_pf, ("ok", "impossible"))
    res = sym.solve(bad)
    assert res.converged[0].all() and not res.converged[1].any()
    viol = evaluate(res, get_rule("pm10"))
    assert viol.solver[1].all() and viol.unsafe[1].all() and not np.isnan(res.u_pu[0]).any()


def test_hot_conductors_raise_the_voltage(network, scn):
    solver = DaySolver(network, asymmetric=False)
    cool = solver.solve(scn).u_pu.max()
    hot_scn = DayScenarioBatch(scn.t, scn.load_kw, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels,
                               ambient_c=np.full(scn.shape, 40.0))
    hot = solver.solve(hot_scn).u_pu.max()
    assert hot > cool
    ref_scn = DayScenarioBatch(scn.t, scn.load_kw, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels,
                               ambient_c=np.full(scn.shape, 10.0))     # 10 + 10 = 20 degrees C: scale exactly 1
    assert abs(solver.solve(ref_scn).u_pu.max() - cool) < 1e-9


def test_volt_watt_caps_rated_power_like_the_legacy_engine(sym, scn):
    # Legacy engine, 9 Oct 2026: 181.2 kWh trimmed, 19 unsafe steps. The cap is on rated power (IEEE 1547), not a cut.
    res = sym.solve(scn, Controls(volt_watt=VoltWattCurve()))
    s = summarise(res, evaluate(res, get_rule("pm10")))
    assert s["curtailed_kwh"] == pytest.approx(181.2, abs=1.0) and s["violation_steps"] == 19


def test_single_phase_homes_leave_volt_var_two_steps_short(network, scn):
    # Measured 9 Oct 2026 (round-robin phases): Volt/VAR alone leaves 2 unsafe steps (254.4 V); adding Volt/Watt clears them.
    solver = DaySolver(network, asymmetric=True)
    vv = summarise(*(lambda r: (r, evaluate(r, get_rule("pm10"))))(solver.solve(scn, Controls(volt_var=VoltVarCurve()))))
    both = solver.solve(scn, Controls(volt_var=VoltVarCurve(), volt_watt=VoltWattCurve()))
    assert vv["violation_steps"] == 2 and summarise(both, evaluate(both, get_rule("pm10")))["violation_steps"] == 0
