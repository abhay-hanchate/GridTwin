import warnings

import pytest

from engine.grid import build_grid, topology
from engine.scenarios import run_scenario

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
    return run_scenario("S4", detail=False)


def test_full_day_runs_cleanly(s4):
    assert len(s4["steps"]) == 96
    assert s4["summary"]["solver_failed_steps"] == 0
    assert 0.8 < s4["summary"]["min_vm_pu"] <= s4["summary"]["max_vm_pu"] < 1.2


def test_solar_causes_violations(s4):
    # Regression reference from the 28 Sep 2026 run: 26 steps, 21 caused by solar.
    assert s4["summary"]["violation_steps_from_solar"] > 0
    assert s4["summary"]["violation_steps"] > s4["summary"]["violation_steps_without_solar"]
