"""control.verify and control.types: storage arithmetic, permitted actions and the physical check of every limit."""
import numpy as np
import pytest

from backend.v2 import compute
from control.execution import Executor, StepInputs
from control.types import Action, BatteryModel, ControlState, Status, SwitchPolicy
from control.verify import action_errors, physical_check


@pytest.fixture(scope="module")
def battery():
    return BatteryModel(kw=20.0, kwh=40.0, efficiency=0.95, soc_min=0.1, soc_max=0.9)


def test_energy_update_uses_efficiency_each_way(battery):
    e = battery.next_energy(20.0, 10.0)                  # charge 10 kW for a quarter hour
    assert e == pytest.approx(20.0 + 0.25 * 10.0 * 0.95)
    assert battery.next_energy(20.0, -10.0) == pytest.approx(20.0 - 0.25 * 10.0 / 0.95)
    assert battery.round_trip == pytest.approx(0.95 ** 2)


def test_power_room_follows_the_energy_left(battery):
    full = battery.kwh * battery.soc_max
    assert battery.max_charge_kw(full) == pytest.approx(0.0)
    assert battery.max_discharge_kw(battery.kwh * battery.soc_min) == pytest.approx(0.0)
    assert battery.max_charge_kw(battery.kwh * 0.5) == pytest.approx(20.0)            # limited by the rating


def test_an_action_that_overcharges_or_breaks_a_rule_is_invalid(battery):
    policy = SwitchPolicy(allowed=("tie_1",), max_operations=2, dwell_steps=8)
    state = ControlState(energy_kwh=battery.kwh * 0.89, topology_id="base", operations_used=0, last_switch_step=None)
    assert any("above" in e for e in action_errors(state, Action(battery_kw=20.0), battery, policy, step=10))
    assert action_errors(state, Action(battery_kw=0.0), battery, policy, step=10) == []
    assert any("not permitted" in e for e in
               action_errors(state, Action(battery_kw=0.0, topology_id="tie_9"), battery, policy, step=10))
    assert any("kept" in e for e in action_errors(state, Action(keep=(1.2, 1.0, 1.0)), battery, policy, step=10))
    used = ControlState(energy_kwh=20.0, topology_id="base", operations_used=2, last_switch_step=0)
    assert any("budget" in e for e in action_errors(used, Action(topology_id="tie_1"), battery, policy, step=20))
    recent = ControlState(energy_kwh=20.0, topology_id="base", operations_used=0, last_switch_step=5)
    assert any("dwell" in e for e in action_errors(recent, Action(topology_id="tie_1"), battery, policy, step=8))


def test_physical_check_flags_every_declared_limit_and_never_passes_a_failed_solve():
    net = compute.network("benchmark_250")
    scn = compute.robust_set(compute.scenarios("2025-05-15", net, 20))
    ex = Executor(net, battery_node=int(net.house_node[-1]), battery_kw_max=30.0)
    inp = StepInputs(scn.load_kw[:, [10, 48]], scn.pv_per_kwp[:, [10, 48]], scn.upstream_pu[:, [10, 48]], scn.t[[10, 48]])
    res = ex.solve(inp, np.zeros(2), np.ones((2, 3)))
    rule = compute.rule("pm10")
    chk = physical_check(res, rule)
    worst = np.nanmax(res.u_pu, axis=(2, 3)) * 230
    assert (chk.safe == (worst <= rule.vmax_v) & (np.nanmin(res.u_pu, axis=(2, 3)) * 230 >= rule.vmin_v)).all()
    assert chk.v_max_v == pytest.approx(worst)
    res.converged[0, 0] = False                                                       # a failed solve is never safe
    chk = physical_check(res, rule)
    assert not chk.safe[0, 0] and np.isinf(chk.severity[0, 0]) and any("solver" in r for r in chk.reasons[0][0])
    tight = physical_check(res, rule, vuf_limit=0.0)                                  # unbalance only when declared
    assert not tight.safe.any()
    assert Status.VERIFIED_SAFE.value == "verified_safe"
