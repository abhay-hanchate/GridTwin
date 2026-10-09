"""D5: radial-safe feeder reconfiguration.

A tie joins the ends of two different feeders; closing it makes one loop, so one line on that loop must be opened
to stay radial. Candidates are (tie, line to open) pairs; every candidate is verified by the power flow.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from engine.types import Network


@dataclass(frozen=True)
class Reconfiguration:
    tie: tuple[int, int]            # nodes joined by the new line
    opened_line: int                # index of the line removed from the original network
    tie_length_m: float
    operations: int = 2             # one closing and one opening


def _graph(network: Network) -> nx.Graph:
    g = nx.Graph()
    for k, (a, b) in enumerate(zip(network.line_from, network.line_to)):
        g.add_edge(int(a), int(b), line=k)
    return g


def feeder_of(network: Network) -> dict[int, int]:
    """Which feeder (child subtree of the transformer's LV node) each node belongs to."""
    g, root = _graph(network), int(network.trafo.to_node)
    out = {root: -1}
    for k, child in enumerate(sorted(g.neighbors(root))):
        for n in nx.node_connected_component(g.subgraph(set(g.nodes) - {root}), child):
            out[n] = k
    return out


def candidate_ties(network: Network, max_distance_m: float = 150.0, max_ties: int = 6) -> list[tuple[int, int, float]]:
    """Pairs of feeder-end nodes on different feeders within `max_distance_m`, nearest first."""
    if network.node_xy is None:
        return []
    g, feeder = _graph(network), feeder_of(network)
    ends = [n for n in g.nodes if g.degree[n] == 1 and n in feeder]
    pairs = []
    for i, u in enumerate(ends):
        for v in ends[i + 1:]:
            if feeder[u] != feeder[v]:
                d = float(np.linalg.norm(network.node_xy[u] - network.node_xy[v]))
                if d <= max_distance_m:
                    pairs.append((u, v, d))
    return sorted(pairs, key=lambda p: p[2])[:max_ties]


def apply(network: Network, rec: Reconfiguration) -> Network:
    """Network after closing the tie and opening the chosen line; the tie uses the street's median per-metre impedance."""
    length = np.maximum(network.line_length_m, 1.0)
    per_m = lambda total: float(np.median(total / length))  # noqa: E731
    new = {"from": rec.tie[0], "to": rec.tie[1], "length_m": rec.tie_length_m,
           "r1": per_m(network.line_r1_ohm) * rec.tie_length_m, "x1": per_m(network.line_x1_ohm) * rec.tie_length_m,
           "r0": per_m(network.line_r0_ohm) * rec.tie_length_m, "x0": per_m(network.line_x0_ohm) * rec.tie_length_m,
           "c1": per_m(network.line_c1_f) * rec.tie_length_m, "i_n": float(np.median(network.line_i_n_a))}
    return network.with_topology(add=[new], remove=[rec.opened_line])


def candidates(network: Network, max_distance_m: float = 150.0, max_ties: int = 6) -> list[Reconfiguration]:
    g = _graph(network)
    out = []
    for u, v, d in candidate_ties(network, max_distance_m, max_ties):
        path = nx.shortest_path(g, u, v)                       # the loop that the tie closes
        for a, b in zip(path[:-1], path[1:]):
            out.append(Reconfiguration((u, v), int(g.edges[a, b]["line"]), d))
    return out
