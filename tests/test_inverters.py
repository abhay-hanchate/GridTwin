import warnings

import numpy as np
import pytest

from engine.actions import ACTIONS
from engine.grid import build_grid
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.powerflow import day_inputs, run_day
from engine.simulate import ACTIONS_BY_ID, worst_bus

warnings.filterwarnings("ignore")


def test_volt_var_curve_matches_ieee_cat_b_points():
    c = VoltVarCurve()
    assert c.q_fraction(1.00) == 0.0 and c.q_fraction(1.02) == 0.0
    assert c.q_fraction(0.92) == pytest.approx(0.44)
    assert c.q_fraction(1.08) == pytest.approx(-0.44)
    assert c.q_fraction(1.05) == pytest.approx(-0.22)
    assert c.q_fraction(1.20) == pytest.approx(-0.44)      # flat beyond the last point
    assert np.allclose(c.q_fraction(np.array([0.98, 1.08])), [0.0, -0.44])


def test_volt_watt_is_a_limit_on_rated_power():
    c = VoltWattCurve()
    assert c.p_fraction(1.05) == 1.0
    assert c.p_fraction(1.08) == pytest.approx(0.6)
    assert c.p_fraction(1.12) == pytest.approx(0.2)


def test_round_one_setting_is_kept_only_as_a_labelled_baseline():
    ids = [a.id for a in ACTIONS]
    assert {"volt_var", "volt_watt", "volt_var_watt", "tap1_volt_var", "pf09_fixed"} <= set(ids)
    assert "not a standard curve" in ACTIONS_BY_ID["pf09_fixed"].label
    assert ACTIONS_BY_ID["volt_var"].params["q_fraction_of_rated_va"] == [0.44, 0.0, 0.0, -0.44]


@pytest.fixture(scope="module")
def inputs():
    return day_inputs("2019-05-15")


@pytest.fixture(scope="module")
def baseline(inputs):
    return run_day(build_grid(1.0), inputs, detail=True)


def _run(action_id, inputs, baseline):
    net = build_grid(1.0)
    hook = ACTIONS_BY_ID[action_id].make_hook(net, worst_bus(baseline), baseline["limits"]["vm_max_pu"])
    return run_day(net, inputs, hook=hook, detail=False)["summary"], hook


def test_standard_volt_var_clears_the_every_home_day(inputs, baseline):
    # Measured 9 Oct 2026: 0 unsafe steps, 220.5-250.1 V, no solar wasted, 8 iterations per step on average.
    r, hook = _run("volt_var", inputs, baseline)
    assert r["violation_steps"] == 0 and r["solver_failed_steps"] == 0
    assert r["max_vm_pu"] * 230 == pytest.approx(250.1, abs=0.5)
    assert r["min_vm_pu"] * 230 == pytest.approx(220.5, abs=0.5)
    assert r["curtailed_kwh"] == 0.0
    assert r["max_vm_pu"] < baseline["summary"]["max_vm_pu"]
    assert max(hook.control.iterations) < hook.control.max_iter


def test_volt_watt_alone_trims_solar_but_does_not_clear_the_day(inputs, baseline):
    # Measured 9 Oct 2026: 181 kWh trimmed, 19 unsafe steps remain (the curve stops at 20% output at 1.10 pu).
    r, _ = _run("volt_watt", inputs, baseline)
    assert r["solver_failed_steps"] == 0
    assert r["curtailed_kwh"] > 100
    assert 0 < r["violation_steps"] < baseline["summary"]["violation_steps"]
    assert r["max_vm_pu"] < baseline["summary"]["max_vm_pu"]
