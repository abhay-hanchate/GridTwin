"""control.execution: explicit battery power (unity power factor) and per-phase-group curtailment, solved by the real
three-phase solver, without the reactive battery rule and without any change to engine/."""
import numpy as np
import pytest

from backend.v2 import compute
from control.execution import Executor, StepInputs

DATE = "2025-05-15"


@pytest.fixture(scope="module")
def setup():
    net = compute.network("benchmark_250")
    scn = compute.robust_set(compute.scenarios(DATE, net, 20))
    ex = Executor(net, battery_node=int(net.house_node[-1]), battery_kw_max=30.0)
    return net, scn, ex


def _inputs(scn, steps):
    return StepInputs(load_kw=scn.load_kw[:, steps], pv_per_kwp=scn.pv_per_kwp[:, steps],
                      upstream_pu=scn.upstream_pu[:, steps], t=scn.t[steps])


def test_idle_battery_and_no_curtailment_match_the_plain_solver(setup):
    net, scn, ex = setup
    steps = [40, 48, 80]
    res = ex.solve(_inputs(scn, steps), battery_kw=np.zeros(3), keep=np.ones((3, 3)))
    from engine.solver import DaySolver
    from engine.types import DayScenarioBatch
    plain = DaySolver(net, asymmetric=True).solve(DayScenarioBatch(
        scn.t[steps], scn.load_kw[:, steps], scn.pv_per_kwp[:, steps], scn.upstream_pu[:, steps], scn.load_pf, scn.labels))
    lv = list(ex.network("base").lv_nodes)
    homes_v = res.u_pu[:, :, [lv.index(int(n)) for n in net.house_node], :]
    plain_v = plain.u_pu[:, :, [list(net.lv_nodes).index(int(n)) for n in net.house_node], :]
    assert np.nanmax(np.abs(homes_v - plain_v)) < 1e-6


def test_curtailing_a_phase_group_delivers_exactly_the_kept_share(setup):
    net, scn, ex = setup
    steps = [48]
    full = ex.solve(_inputs(scn, steps), battery_kw=np.zeros(1), keep=np.ones((1, 3)))
    half_a = ex.solve(_inputs(scn, steps), battery_kw=np.zeros(1), keep=np.array([[0.5, 1.0, 1.0]]))
    avail_a = (scn.pv_per_kwp[:, 48:49] * net.house_kwp[net.house_phase == 0].sum())        # (S, 1) kW on phase A
    assert half_a.pv_kw == pytest.approx(full.pv_kw - 0.5 * avail_a, abs=1e-6)
    assert np.nanmax(half_a.u_pu) < np.nanmax(full.u_pu)                                  # less export, lower peak


def test_battery_charging_is_unity_power_factor_and_lowers_the_noon_peak(setup):
    net, scn, ex = setup
    steps = [48]
    idle = ex.solve(_inputs(scn, steps), battery_kw=np.zeros(1), keep=np.ones((1, 3)))
    charge = ex.solve(_inputs(scn, steps), battery_kw=np.array([20.0]), keep=np.ones((1, 3)))
    assert charge.battery_kw == pytest.approx(np.full((3, 1), 20.0))
    assert np.nanmax(charge.u_pu) < np.nanmax(idle.u_pu)
    assert ex.load_pf()[-3:] == pytest.approx([1.0, 1.0, 1.0])                         # no hidden reactive power
    # transformer power rises by the charge plus a little loss: active power only, no reactive coupling
    assert (charge.trafo_p_kw - idle.trafo_p_kw) == pytest.approx(np.full((3, 1), 20.0), abs=1.5)


def test_battery_power_beyond_its_rating_is_refused(setup):
    _, scn, ex = setup
    with pytest.raises(ValueError, match="rating"):
        ex.solve(_inputs(scn, [48]), battery_kw=np.array([31.0]), keep=np.ones((1, 3)))
