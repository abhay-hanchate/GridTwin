import warnings

import numpy as np
import pytest

from engine.archetypes import build
from engine.dayinputs import scenarios_from_legacy
from engine.headroom import probe_nodes
from engine.planning_extra import downstream_homes, rank_meter_sites, rank_transformers, rx_map
from engine.powerflow import day_inputs
from engine.rules import get_rule

warnings.filterwarnings("ignore")


def _street(aid="benchmark_250"):
    net = build(aid, phases="round_robin")
    net = net.with_pv(net.house_kwp * (np.arange(net.n_homes) % 10 < 3))
    return net, scenarios_from_legacy(day_inputs("2019-05-15"), net)


@pytest.fixture(scope="module")
def street():
    return _street()


def test_downstream_homes_counts_every_home_at_the_transformer(street):
    net, _ = street
    assert downstream_homes(net)[net.trafo.to_node] == net.n_homes


def test_meter_ranking_prefers_the_far_end(street):
    net, scn = street
    rows = rank_meter_sites(net, scn)
    nodes = probe_nodes(net)
    rank = {r["node"]: i for i, r in enumerate(rows)}
    assert rows[0]["score"] >= rows[-1]["score"] and rows[0]["dv_per_kw_v"] > 0
    far = next(r for r in rows if r["node"] == nodes["far"])
    near = next(r for r in rows if r["node"] == nodes["near"])
    assert far["dv_per_kw_v"] > near["dv_per_kw_v"]                     # voltage rises more per kW far away
    assert len(rank) == len(set(int(n) for n in net.house_node))


def test_rx_map_reports_every_cell(street):
    # Measured 9 Oct 2026 (Volt/VAR peak reduction): R x0.5 1.9 V, R x2 5.3 V; X x0.5 2.0 V, X x2 1.7 V. The curve's
    # feedback (it absorbs more where voltage is higher) dominates, so the map reports cells and claims no rule.
    net, scn = street
    m = rx_map(net, scn, get_rule("pm10"), r_scales=(0.5, 2.0), x_scales=(1.0,))
    assert len(m["cells"]) == 2 and m["cells"][1]["r_over_x"] > m["cells"][0]["r_over_x"]
    assert all(c["peak_v_volt_var"] <= c["peak_v_without"] for c in m["cells"])


def test_transformer_ranking_boosts_unmetered_and_loaded_ones(street):
    net, scn = street
    item = lambda i, kw, metered: {"id": i, "network": net, "scenarios": scn, "connected_kw": kw, "metered": metered}  # noqa: E731
    rows = rank_transformers([item("light", 5, True), item("heavy", 60, True), item("blind", 5, False)], get_rule("pm10"))
    order = [r["id"] for r in rows]
    assert order.index("heavy") < order.index("light") and order.index("blind") < order.index("light")
    with pytest.raises(ValueError, match="empty"):
        rank_transformers([], get_rule("pm10"))
