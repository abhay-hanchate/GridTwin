import numpy as np
import pandas as pd
import pytest

from engine.rules import get_rule
from engine.types import DayResult
from engine.violations import evaluate, summarise


def _result(s=1, t=4, n=3):
    z = lambda *shape: np.zeros(shape)  # noqa: E731
    return DayResult(
        t=pd.date_range("2025-05-15", periods=t, freq="15min"), u_pu=np.full((s, t, n, 3), 1.0),
        line_loading_pct=z(s, t, 2), trafo_loading_pct=z(s, t), trafo_p_kw=np.full((s, t), 5.0), losses_kw=np.full((s, t), 0.4),
        q_loss_kvar=np.full((s, t), 0.1), pv_kw=np.full((s, t), 8.0), pv_avail_kw=np.full((s, t), 10.0), inverter_kvar=z(s, t),
        battery_kw=z(s, t), neutral_a=z(s, t), vuf_pct=z(s, t), converged=np.ones((s, t), dtype=bool))


def test_a_clean_day_has_no_violations():
    v = evaluate(_result(), get_rule("pm10"))
    assert not v.unsafe.any() and v.rule_id == "pm10"


def test_each_limit_is_detected_on_its_own_step():
    r = _result()
    r.u_pu[0, 0, 1, 2] = 1.11             # over, on phase C of one node
    r.u_pu[0, 1, 0, 0] = 0.89             # under
    r.line_loading_pct[0, 2, 1] = 101     # line overload
    r.trafo_loading_pct[0, 3] = 100.5     # transformer overload
    v = evaluate(r, get_rule("pm10"))
    assert v.over[0].tolist() == [True, False, False, False] and v.under[0].tolist() == [False, True, False, False]
    assert v.line[0].tolist() == [False, False, True, False] and v.trafo[0].tolist() == [False, False, False, True]
    assert v.unsafe.all()


def test_the_rule_decides_the_band():
    r = _result()
    r.u_pu[0, 0, 0, 0] = 1.07
    assert not evaluate(r, get_rule("pm10")).unsafe.any()
    assert evaluate(r, get_rule("up_2005")).over[0, 0]          # +-6% band


def test_solver_failure_is_unsafe_even_with_nan_voltages():
    r = _result()
    r.converged[0, 2] = False
    r.u_pu[0, 2] = np.nan
    v = evaluate(r, get_rule("pm10"))
    assert v.solver[0, 2] and v.unsafe[0, 2] and not v.over[0, 2] and not v.under[0, 2]


def test_voltage_unbalance_is_only_a_violation_when_a_limit_is_given():
    r = _result()
    r.vuf_pct[0, 1] = 3.5
    assert not evaluate(r, get_rule("pm10")).unsafe.any()
    assert evaluate(r, get_rule("pm10"), vuf_limit=2.0).unbalance[0].tolist() == [False, True, False, False]


def test_summary_keys_and_cost_accounting():
    r = _result()
    r.u_pu[0, 1, 0, 0] = 1.12
    r.trafo_p_kw[0, 3] = -2.0             # reverse flow
    r.inverter_kvar[0, :] = [1, 1, -1, 0]
    s = summarise(r, evaluate(r, get_rule("pm10")))
    assert s["violation_steps"] == 1 and s["solver_failed_steps"] == 0 and s["reverse_flow_steps"] == 1
    assert s["max_vm_pu"] == 1.12
    assert s["curtailed_kwh"] == pytest.approx(2.0 * 4 * 0.25)     # 2 kW lost for 4 steps of 0.25 h
    assert s["pv_kwh"] == pytest.approx(8.0)
    assert s["inverter_kvarh"] == pytest.approx(0.5)               # only absorption counts
    assert s["losses_kwh"] == pytest.approx(0.4)
