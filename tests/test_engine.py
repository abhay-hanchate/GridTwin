import warnings

import pytest

from engine.grid import build_grid, topology
from engine.powerflow import day_inputs, run_day

DAY = "2019-05-15"


def run_street(pv_share: float) -> dict:
    """The reference day on the benchmark street with `pv_share` of homes on 3 kW solar, plus the no-solar baseline."""
    inputs = day_inputs(DAY)
    result = run_day(build_grid(pv_share), inputs, band="10", detail=False)
    baseline = run_day(build_grid(0.0), inputs, band="10", detail=False)
    result["summary"]["violation_steps_without_solar"] = baseline["summary"]["violation_steps"]
    result["summary"]["violation_steps_from_solar"] = (
        result["summary"]["violation_steps"] - baseline["summary"]["violation_steps"])
    return result

warnings.filterwarnings("ignore")


def test_grid_has_indian_overhead_lines_and_working_taps():
    net = build_grid(0.5)
    lv = net.line.from_bus.map(net.bus.vn_kv) < 1
    assert (net.line.loc[lv, "r_ohm_per_km"] == 0.5524).all()
    assert (net.trafo.tap_changer_type == "Ratio").all()
    assert len(net.sgen) == round(0.5 * len(net.load))


def test_topology_has_coordinates():
    topo = topology(build_grid(0.0))
    assert len(topo["buses"]) == 96 and len(topo["lines"]) == 95
    assert all(isinstance(b["x"], float) for b in topo["buses"])


@pytest.fixture(scope="module")
def s4():
    return run_street(1.0)


def test_full_day_runs_cleanly(s4):
    assert len(s4["steps"]) == 96
    assert s4["summary"]["solver_failed_steps"] == 0
    assert 0.8 < s4["summary"]["min_vm_pu"] <= s4["summary"]["max_vm_pu"] < 1.2


def test_solar_causes_violations(s4):
    # Regression reference from the 28 Sep 2026 run: 26 steps, 21 caused by solar.
    assert s4["summary"]["violation_steps_from_solar"] > 0
    assert s4["summary"]["violation_steps"] > s4["summary"]["violation_steps_without_solar"]


import pandapower as pp  # noqa: E402


@pytest.fixture(scope="module")
def s1():
    return run_street(0.0)


def test_solver_failure_counts_as_unsafe(monkeypatch):
    real = pp.runpp
    calls = {"n": 0}

    def flaky(net, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 4:
            raise pp.LoadflowNotConverged("forced")
        return real(net, *args, **kwargs)

    monkeypatch.setattr(pp, "runpp", flaky)
    r = run_day(build_grid(0.0), day_inputs("2019-05-15"), detail=False)
    assert r["summary"]["solver_failed_steps"] == 1
    failed = [s for s in r["steps"] if s.get("solver_failed")]
    assert failed[0]["violations"][0]["type"] == "solver_failure"
    assert r["summary"]["violation_steps"] >= 1


def test_reverse_flow_appears_only_with_solar(s4, s1):
    assert s4["summary"]["reverse_flow_steps"] > 0
    assert s1["summary"]["reverse_flow_steps"] == 0


def test_cost_accounting_fields_are_present_and_sane(s4):
    sm = s4["summary"]
    assert 40 < sm["max_trafo_loading_pct"] < 50
    assert sm["reactive_loss_kvarh"] > 0
    assert sm["inverter_kvarh"] == 0                        # no inverter control in a plain scenario run


def test_binding_limit_is_named_for_the_every_home_day(s4):
    limit = s4["summary"]["binding_limit"]
    assert limit["type"] == "overvoltage" and limit["steps"] == s4["summary"]["violation_steps"]
