"""control.planner: sequential linear programming over a 16-step horizon, checked in the real solver."""
import numpy as np
import pytest

from backend.v2 import compute
from control.execution import Executor, StepInputs
from control.planner import PlannerConfig, plan
from control.types import BatteryModel, ControlState

NOON = list(range(44, 60))                     # 11:00 to 14:45, the solar peak, 16 steps


@pytest.fixture(scope="module")
def world():
    net = compute.network("benchmark_250")
    scn = compute.robust_set(compute.scenarios("2025-05-15", net, 20))
    node = int(net.house_node[-1])
    ex = Executor(net, battery_node=node, battery_kw_max=30.0)
    fc = StepInputs(scn.load_kw[:, NOON], scn.pv_per_kwp[:, NOON], scn.upstream_pu[:, NOON], scn.t[NOON])
    return ex, fc, compute.rule("pm10")


BAT = BatteryModel(kw=30.0, kwh=60.0)


def _ok_storage(p, bat, e0):
    e = [e0]
    for x in p:
        e.append(bat.next_energy(e[-1], x))
    return min(e) >= bat.e_min - 1e-6 and max(e) <= bat.e_max + 1e-6


def test_coordinated_plan_is_safe_in_the_real_solver_for_every_retained_scenario(world):
    ex, fc, rule = world
    out = plan(ex, fc, ControlState(energy_kwh=30.0), BAT, rule, PlannerConfig())
    assert out.horizon == 16 >= 8
    assert out.verified, out.summary()
    assert out.check.safe.all()                                    # every scenario, every step, real solver
    assert out.curtailed_kwh > 0                                   # a 30 kW battery alone cannot hold ~270 V
    assert _ok_storage(out.battery_kw, BAT, 30.0)
    assert not np.any((out.charge_kw > 1e-6) & (out.discharge_kw > 1e-6))     # never both at once
    assert ((out.keep >= -1e-9) & (out.keep <= 1 + 1e-9)).all()


def test_battery_only_plan_reports_the_steps_it_cannot_make_safe(world):
    ex, fc, rule = world
    out = plan(ex, fc, ControlState(energy_kwh=30.0), BAT, rule, PlannerConfig(curtail=False))
    assert not out.verified
    assert out.predicted_infeasible_steps                          # interval-level diagnosis, not a day-level verdict
    assert (out.keep == 1.0).all()
    assert _ok_storage(out.battery_kw, BAT, 30.0)
    assert out.battery_kw.max() > 0                                # it still charges where that helps


def test_a_full_battery_cannot_be_planned_to_charge(world):
    ex, fc, rule = world
    out = plan(ex, fc, ControlState(energy_kwh=BAT.e_max), BAT, rule, PlannerConfig())
    assert out.charge_kw[0] == pytest.approx(0.0, abs=1e-6)
    assert _ok_storage(out.battery_kw, BAT, BAT.e_max)


def test_a_warm_start_longer_than_a_shortened_end_of_day_horizon_is_trimmed(world):
    ex, fc, rule = world
    short = fc.take(list(range(10)))
    warm = (np.zeros(16), np.ones((16, 3)))
    out = plan(ex, short, ControlState(energy_kwh=30.0), BAT, rule, PlannerConfig(), warm=warm)
    assert out.horizon == 10
