"""E4 meter-first ranking, E6 R/X sensitivity of Volt/VAR, and transformer ranking across a portfolio (P7.4, P7.6, P7.7).

(The plan's stress lab, E5, is the /whatif registry: engine.registry changes for panel size, grid voltage, EV
charging and heatwave demand, combined with any registered fix.)
"""
from __future__ import annotations

from dataclasses import replace

import networkx as nx
import numpy as np

from engine.headroom import electrical_distance, headroom, with_new_homes
from engine.inverters import VoltVarCurve
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch, Network

PROBE_KW = 1.0
UNMETERED_BOOST = 1.5


def _peak_step(network: Network, scn: DayScenarioBatch) -> DayScenarioBatch:
    """The single step with the highest voltage of the first scenario (where a meter matters most)."""
    res = DaySolver(network, asymmetric=True).solve(scn)
    i = int(np.nanmax(res.u_pu[0], axis=(1, 2)).argmax())
    return DayScenarioBatch(scn.t[i:i + 1], scn.load_kw[:1, i:i + 1], scn.pv_per_kwp[:1, i:i + 1],
                            scn.upstream_pu[:1, i:i + 1], scn.load_pf, scn.labels[:1])


def downstream_homes(network: Network) -> dict[int, int]:
    """Number of homes at or beyond each node, seen from the transformer."""
    g = nx.Graph()
    g.add_edges_from((int(a), int(b)) for a, b in zip(network.line_from, network.line_to))
    tree = nx.bfs_tree(g, network.trafo.to_node)
    homes = np.bincount(network.house_node, minlength=network.n_nodes)
    return {int(n): int(homes[list(nx.descendants(tree, n) | {n})].sum()) for n in tree.nodes}


def rank_meter_sites(network: Network, scn: DayScenarioBatch) -> list[dict]:
    """Nodes ordered by the value of a smart meter there: voltage rise per kW at the peak step x homes downstream."""
    step = _peak_step(network, scn)
    base = DaySolver(network, asymmetric=True).solve(step).u_pu[0, 0]
    lv = list(network.lv_nodes)
    down = downstream_homes(network)
    dist = electrical_distance(network)
    rows = []
    for node in sorted(set(int(n) for n in network.house_node)):
        i = lv.index(node)
        net, s = with_new_homes(network, step, node, 0, 0.0)
        s = replace(s, load_kw=s.load_kw.copy())
        s.load_kw[..., -1] = -PROBE_KW               # a direct 1 kW injection: the peak may be when there is little sun
        dv = float(np.nanmax(DaySolver(net, asymmetric=True).solve(s).u_pu[0, 0, i]) - np.nanmax(base[i])) * 230
        rows.append({"node": node, "dv_per_kw_v": round(dv, 3), "homes_downstream": down.get(node, 0),
                     "distance_m": round(dist[node], 1), "score": round(dv * down.get(node, 0), 3)})
    return sorted(rows, key=lambda r: -r["score"])


def rx_map(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, r_scales=(0.5, 1.0, 1.5, 2.0),
           x_scales=(0.5, 1.0, 1.5, 2.0)) -> dict:
    """Peak voltage with and without standard Volt/VAR as line R and X are scaled (reactance is an estimate here)."""
    lv_line = np.isin(network.line_from, network.lv_nodes) & np.isin(network.line_to, network.lv_nodes)
    cells = []
    for rs in r_scales:
        for xs in x_scales:
            net = network.replace(line_r1_ohm=np.where(lv_line, network.line_r1_ohm * rs, network.line_r1_ohm),
                                  line_x1_ohm=np.where(lv_line, network.line_x1_ohm * xs, network.line_x1_ohm),
                                  line_r0_ohm=np.where(lv_line, network.line_r0_ohm * rs, network.line_r0_ohm),
                                  line_x0_ohm=np.where(lv_line, network.line_x0_ohm * xs, network.line_x0_ohm))
            solver = DaySolver(net, asymmetric=True)
            none, vv = solver.solve(scn), solver.solve(scn, Controls(volt_var=VoltVarCurve()))
            peak = lambda r: float(np.nanmax(r.u_pu)) * 230  # noqa: E731
            cells.append({"r_scale": rs, "x_scale": xs,
                          "r_over_x": round(float(network.line_r1_ohm[lv_line].sum() * rs / (network.line_x1_ohm[lv_line].sum() * xs)), 2),
                          "peak_v_without": round(peak(none), 1), "peak_v_volt_var": round(peak(vv), 1),
                          "volt_var_reduction_v": round(peak(none) - peak(vv), 1)})
    return {"rule": rule.id, "cells": cells,
            "note": "Reactance is an estimate (0.29-0.35 ohm/km); the map doubles as the sensitivity to that estimate. "
                    "Measured on the benchmark street (peak reduction by Volt/VAR): R x0.5 1.9 V, R x2 5.3 V; X x0.5 2.0 V, "
                    "X x2 1.7 V. The curve absorbs more where voltage is higher, and that feedback dominates the "
                    "per-kvar effect of X, so read the cells, not a rule of thumb."}


def rank_transformers(portfolio: list[dict], rule: VoltageRule) -> list[dict]:
    """Transformers ordered by risk of unseen trouble: share of their safe room already used, boosted when unmetered.

    Each item: {id, network, scenarios, connected_kw, metered}. Room = the best no-worse headroom next to the
    transformer (any phase); used share = connected kW / room.
    """
    if not portfolio:
        raise ValueError("the portfolio is empty")
    rows = []
    for item in portfolio:
        h = headroom(item["network"], item["scenarios"], rule)
        room = max(p["no_worse_kw"] for p in h["locations"]["near"]["phases"].values())
        used = item["connected_kw"] / max(room, 0.1)
        rows.append({"id": item["id"], "connected_kw": item["connected_kw"], "headroom_kw": room,
                     "share_of_headroom_used": round(used, 2), "metered": item["metered"],
                     "score": round(used * (1.0 if item["metered"] else UNMETERED_BOOST), 3),
                     "trafo_kva": round(item["network"].trafo.sn_va / 1000, 1)})
    return sorted(rows, key=lambda r: (-r["score"], r["headroom_kw"]))
