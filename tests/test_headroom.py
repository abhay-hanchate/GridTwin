import warnings

import numpy as np
import pytest

from engine.archetypes import build
from engine.dayinputs import scenarios_from_legacy
from engine.headroom import _bisect, check_connection, cumulative_check, headroom, probe_nodes, with_new_homes
from engine.powerflow import day_inputs
from engine.rules import get_rule

warnings.filterwarnings("ignore")
RULE = get_rule("pm10")


def _street(aid="benchmark_250", share=3):
    net = build(aid, phases="round_robin")
    net = net.with_pv(net.house_kwp * (np.arange(net.n_homes) % 10 < share))      # 30% of homes have solar
    return net, scenarios_from_legacy(day_inputs("2019-05-15"), net)


@pytest.fixture(scope="module")
def street():
    return _street()


@pytest.fixture(scope="module")
def room(street):
    return headroom(*street, RULE)


def test_bisect_finds_the_edge():
    assert _bisect(lambda x: x <= 7.3, 60, 0.1) == pytest.approx(7.3, abs=0.1)
    assert _bisect(lambda x: True, 60, 0.1) == 60 and _bisect(lambda x: False, 60, 0.1) == 0


def test_new_homes_extend_the_network_and_the_scenarios(street):
    net, scn = street
    n2, s2 = with_new_homes(net, scn, int(net.house_node[0]), 2, 4.0, count=3)
    assert n2.n_homes == net.n_homes + 3 and s2.load_kw.shape[2] == net.n_homes + 3
    assert (n2.house_kwp[-3:] == 4.0).all() and (s2.load_kw[..., -3:] == 0).all()


def test_the_far_end_has_less_headroom_than_the_transformer_end(room):
    near, far = room["locations"]["near"]["phases"], room["locations"]["far"]["phases"]
    assert max(p["no_worse_kw"] for p in far.values()) < max(p["no_worse_kw"] for p in near.values())
    # Measured 9 Oct 2026: far end 0.5 / 2.8 / 1.9 kW on A / B / C - the phase matters as much as the place.
    assert min(p["no_worse_kw"] for p in far.values()) < 1.0


def test_strict_headroom_is_zero_when_the_street_is_already_unsafe(room):
    assert room["baseline_unsafe_steps"] > 0
    assert all(p["strict_kw"] == 0 for loc in room["locations"].values() for p in loc["phases"].values())


def test_flat_caps_are_reported_beside_the_physics_and_tagged(room):
    assert room["flat_caps"]["Karnataka"]["cap_kw"] == pytest.approx(200.0)       # 80% of 250 kVA
    assert all("not verified" in c["tag"] for c in room["flat_caps"].values())


def test_a_weak_feeder_has_less_headroom():
    weak = headroom(*_street("rural_weak_63"), RULE)
    strong = headroom(*_street("benchmark_250"), RULE)
    best = lambda h: max(p["no_worse_kw"] for p in h["locations"]["near"]["phases"].values())  # noqa: E731
    assert best(weak) < best(strong)


def test_a_small_request_is_approved_on_a_safe_phase(street):
    # Measured 9 Oct 2026: 2 kW at the far end is approved on C; on A it would worsen 11 steps.
    net, scn = street
    c = check_connection(net, scn, RULE, node=probe_nodes(net)["far"], kw=2)
    per = c["evidence"]["per_phase_worsened_steps"]
    assert c["decision"] == "approve" and c["phase"] != "A" and per["A"] > 0 == per[c["phase"]]
    assert "advisory" in c["regulatory_status"]


def test_five_kw_at_the_far_end_needs_standard_volt_var(street):
    net, scn = street
    c = check_connection(net, scn, RULE, node=probe_nodes(net)["far"], kw=5)
    assert c["decision"] == "approve_with_conditions" and "Volt/VAR" in c["conditions"][0]


def test_a_large_far_request_needs_conditions(street):
    net, scn = street
    c = check_connection(net, scn, RULE, node=probe_nodes(net)["far"], kw=40)
    assert c["decision"] in ("approve_with_conditions", "refuse")
    assert c["conditions"] or c["binding_limit"]["type"] == "overvoltage"
    assert "feasibility study expected" in c["regulatory_status"]


def test_exempt_systems_add_up(street):
    net, scn = street
    far = probe_nodes(net)["far"]
    near = probe_nodes(net)["near"]
    cu = cumulative_check(net, scn, RULE, [{"node": far, "phase": 0, "kwp": 9.5}] * 4, {"node": near, "kw": 2})
    assert cu["request_alone"] == "approve" and cu["safe_with_existing"] is False and cu["worsened_steps"] > 0


def test_an_unknown_node_is_rejected(street):
    net, scn = street
    with pytest.raises(ValueError, match="not a low-voltage node"):
        check_connection(net, scn, RULE, node=net.trafo.from_node, kw=3)      # the 11 kV side
