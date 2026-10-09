import warnings

import numpy as np
import pytest

from engine.archetypes import ARCHETYPES, CONDUCTORS, build, list_archetypes
from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.violations import evaluate, summarise

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def inputs():
    return day_inputs("2019-05-15")


def _peak(net, inputs):
    res = DaySolver(net, asymmetric=True).solve(scenarios_from_legacy(inputs, net))
    assert res.converged.all()
    return res, summarise(res, evaluate(res, get_rule("pm10")))


def test_catalogue_lists_every_archetype_with_its_parameters():
    rows = {r["id"]: r for r in list_archetypes()}
    assert set(rows) == set(ARCHETYPES) and rows["rural_weak_63"]["trafo_kva"] == 63.0
    assert CONDUCTORS["rabbit"]["r_ohm_per_km"] == 0.5524            # the Round 1 value, from IS 398


def test_unknown_archetype_is_rejected_with_the_valid_names():
    with pytest.raises(KeyError, match="urban_short_160"):
        build("nowhere")


@pytest.mark.parametrize("aid", list(ARCHETYPES))
def test_every_archetype_is_radial_sized_and_sourced(aid):
    net = build(aid)
    a = ARCHETYPES[aid]
    assert net.is_radial() and net.n_homes == a.n_homes
    assert net.trafo.sn_va == pytest.approx(a.trafo_kva * 1000)
    assert "IS 398" in net.provenance["conductor"] and "benchmark" in net.provenance["topology"]
    assert (net.house_kwp > 0).all() and set(np.unique(net.house_phase)) <= {0, 1, 2}


def test_benchmark_archetype_is_exactly_round_one():
    ref = from_pandapower(build_grid(1.0), phases="random")
    got = build("benchmark_250")
    assert np.allclose(got.line_r1_ohm, ref.line_r1_ohm) and np.array_equal(got.house_node, ref.house_node)
    assert np.array_equal(got.house_phase, ref.house_phase)


def test_longer_and_thinner_feeders_have_more_wire_resistance_and_more_voltage_rise(inputs):
    nets = {aid: build(aid, phases="round_robin") for aid in ("urban_short_160", "suburban_100", "rural_long_100", "rural_weak_63")}
    resistance = {aid: float(n.line_r1_ohm.sum()) for aid, n in nets.items()}
    assert resistance["urban_short_160"] < resistance["suburban_100"] < resistance["rural_long_100"] < resistance["rural_weak_63"]
    peaks = {aid: _peak(n, inputs)[1]["max_vm_pu"] for aid, n in nets.items() if aid != "rural_weak_63"}
    # The weak 63 kVA feeder carries only 40 homes, so its peak is not compared: fewer homes means less rise.
    assert peaks["urban_short_160"] < peaks["suburban_100"] < peaks["rural_long_100"]


def test_a_small_transformer_loads_up_faster_per_home(inputs):
    big, small = build("benchmark_250", phases="round_robin"), build("rural_weak_63", phases="round_robin")
    t_big = _peak(big, inputs)[0].trafo_loading_pct.max() / big.n_homes
    t_small = _peak(small, inputs)[0].trafo_loading_pct.max() / small.n_homes
    assert t_small > t_big
