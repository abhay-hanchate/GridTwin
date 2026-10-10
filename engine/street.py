"""The street as a picture: a schematic layout of the low-voltage tree and per-phase flows on every wire.

Layout: a "metro map". The transformer sits at the left; each wire is one step to the right (hop depth); a branch
keeps its parent's row when it is the parent's largest sub-tree and opens a new row otherwise.

Flows: every wire carries the net power (demand minus delivered solar) of all homes beyond it, phase by phase,
because homes are single-phase. The neutral carries the imbalance: the vector sum of the three phase currents,
which are 120 degrees apart. Losses and reactive power are ignored, so the flows are an estimate from the homes'
net power, not a solver output; the voltages shown beside them are the solver's.
"""
from __future__ import annotations

import networkx as nx
import numpy as np

from engine.types import Controls, DayScenarioBatch, Network

NOMINAL_V = 230.0
_ROT = np.exp(-2j * np.pi / 3) ** np.arange(3)          # phase A, B, C at 0, -120, -240 degrees


def tree(network: Network) -> nx.DiGraph:
    g = nx.Graph()
    g.add_edges_from((int(a), int(b), {"line": i}) for i, (a, b) in enumerate(zip(network.line_from, network.line_to)))
    return nx.bfs_tree(g, network.trafo.to_node), g


def layout(network: Network) -> dict:
    """Node positions (x = hops from the transformer, y = row) and each line oriented away from the transformer.

    Rows are given depth first, so each sub-tree owns a block of consecutive rows: the largest child continues its
    parent's row, the others start below the rows of their elder siblings' sub-trees. A branch's vertical drop sits
    left of everything those sub-trees draw, so no two wires cross."""
    t, g = tree(network)
    root = network.trafo.to_node
    size = {n: len(nx.descendants(t, n)) + 1 for n in t.nodes}
    pos: dict[int, tuple[int, int]] = {}
    next_row = [1]

    def place(n: int, x: int, row: int) -> None:
        pos[n] = (x, row)
        for k, child in enumerate(sorted(t.successors(n), key=lambda c: (-size[c], c))):
            if k == 0:
                place(child, x + 1, row)
            else:
                r = next_row[0]
                next_row[0] += 1
                place(child, x + 1, r)

    place(root, 0, 0)
    lines = [{"line": int(g.edges[a, b]["line"]), "from": int(a), "to": int(b)} for a, b in t.edges]
    return {"root": int(root), "nodes": [{"id": int(n), "x": int(p[0]), "y": int(p[1])} for n, p in sorted(pos.items())],
            "lines": sorted(lines, key=lambda r: r["line"]), "rows": next_row[0]}


def home_net_kw(network: Network, scn: DayScenarioBatch, controls: Controls = Controls(), s: int = 0) -> np.ndarray:
    """(T, H) demand minus delivered solar per home for scenario `s`, with curtailment and export limits applied
    the way the solver applies them (Volt/Watt's extra reduction is not included)."""
    load = scn.load_kw[s]
    pv = scn.pv_per_kwp[s][:, None] * network.house_kwp[None, :]
    if controls.curtail_keep is not None:
        pv = pv * controls.curtail_keep
    if controls.export_limit_kw is not None:
        lim = np.broadcast_to(np.asarray(controls.export_limit_kw, float), load.shape)
        pv = np.minimum(pv, load + lim)
    return load - pv


def line_flows(network: Network, net_kw: np.ndarray) -> dict:
    """Per line: (T, 3) phase power in kW (positive = towards the homes) and (T,) neutral current in A."""
    t, g = tree(network)
    homes_at = {}
    for h, node in enumerate(network.house_node):
        homes_at.setdefault(int(node), []).append(h)
    phase_kw = np.zeros((network.n_lines, net_kw.shape[0], 3))
    for a, b in t.edges:
        beyond = [h for n in nx.descendants(t, b) | {b} for h in homes_at.get(n, [])]
        for ph in range(3):
            sel = [h for h in beyond if network.house_phase[h] == ph]
            if sel:
                phase_kw[g.edges[a, b]["line"], :, ph] = net_kw[:, sel].sum(axis=1)
    amps = phase_kw * 1000.0 / NOMINAL_V
    neutral = np.abs((amps * _ROT[None, None, :]).sum(axis=2))
    return {"phase_kw": phase_kw, "neutral_a": neutral}
