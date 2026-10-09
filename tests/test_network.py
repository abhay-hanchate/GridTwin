import warnings

import numpy as np
import pytest

from engine.grid import build_grid
from engine.network import assign_phases, from_pandapower

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def pp_net():
    return build_grid(1.0)


@pytest.fixture(scope="module")
def network(pp_net):
    return from_pandapower(pp_net, phases="round_robin")


def test_assign_phases_modes():
    assert assign_phases(7, "round_robin").tolist() == [0, 1, 2, 0, 1, 2, 0]
    assert assign_phases(5, "all_a").tolist() == [0] * 5
    a, b = assign_phases(60, "random", seed=1), assign_phases(60, "random", seed=1)
    assert a.tolist() == b.tolist() and set(a.tolist()) == {0, 1, 2}
    with pytest.raises(ValueError, match="unknown phase mode"):
        assign_phases(3, "diagonal")


def test_conversion_keeps_the_pandapower_structure(pp_net, network):
    assert network.n_homes == len(pp_net.load) == 99
    assert network.n_lines == len(pp_net.line)
    assert network.n_nodes == len(pp_net.bus)
    assert network.house_kwp.sum() == pytest.approx(pp_net.sgen.sn_mva.sum() * 1000)
    assert (network.house_kwp > 0).all()                        # 100% adoption, one system per home
    assert network.trafo.sn_va == pytest.approx(250e3)


def test_zero_sequence_is_an_explicit_multiple_of_positive_sequence(pp_net):
    n = from_pandapower(pp_net, r0_ratio=4.0, x0_ratio=2.0)
    assert np.allclose(n.line_r0_ohm, 4 * n.line_r1_ohm) and np.allclose(n.line_x0_ohm, 2 * n.line_x1_ohm)
    assert "unsourced" in n.provenance["zero_sequence"]


def test_the_converted_feeder_is_radial_and_a_loop_is_detected(network):
    assert network.is_radial()
    lv = network.lv_nodes
    tie = {"from": int(lv[0]), "to": int(lv[-1]), "r1": 0.1, "x1": 0.03, "r0": 0.3, "x0": 0.09, "c1": 0.0, "i_n": 200.0, "length_m": 50.0}
    assert not network.with_topology(add=[tie]).is_radial()
    assert network.with_topology(add=[tie], remove=[0]).n_lines == network.n_lines


def test_copies_do_not_change_the_original(network):
    moved = network.with_phases(np.zeros(network.n_homes, dtype=int)).with_pv(np.zeros(network.n_homes))
    assert moved.house_phase.sum() == 0 and moved.house_kwp.sum() == 0
    assert network.house_phase.sum() > 0 and network.house_kwp.sum() > 0
