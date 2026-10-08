"""A4: Indian low-voltage feeder archetypes built on the 99-home benchmark topology.

The topology is a German benchmark (SimBench 1-LV-rural2); what is Indian is the conductor (IS 398 Part II
ACSR resistance and ampacity), the feeder length, the distribution-transformer rating and the number of homes.
Reactance is not in the standard table used here: 0.29 ohm/km is an ESTIMATE (log formula, 0.4 m spacing)
and is labelled as such in `Network.provenance`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import networkx as nx
import numpy as np

from engine.grid import build_grid
from engine.network import assign_phases, from_pandapower
from engine.types import Network

X_ESTIMATE_OHM_PER_KM = 0.29
BENCHMARK_X_OHM_PER_KM = 0.35               # Round 1 value, kept for the benchmark archetype only
ZERO_SEQUENCE_RATIO = 3.0                   # unsourced; see gate G5

# IS 398 Part II (scanned reproduction; verify against the BIS copy): DC resistance at 20 degrees C in ohm/km,
# current rating at 75 degrees C conductor temperature in A.
CONDUCTORS = {
    "squirrel": {"r_ohm_per_km": 1.3940, "i_a": 89},
    "weasel": {"r_ohm_per_km": 0.9289, "i_a": 114},
    "rabbit": {"r_ohm_per_km": 0.5524, "i_a": 155},
    "racoon": {"r_ohm_per_km": 0.3712, "i_a": 196},
    "dog": {"r_ohm_per_km": 0.2792, "i_a": 231},
}


@dataclass(frozen=True)
class Archetype:
    id: str
    label: str
    conductor: str
    length_scale: float        # multiplies the benchmark's cable lengths
    trafo_kva: float
    n_homes: int
    x_ohm_per_km: float = X_ESTIMATE_OHM_PER_KM
    note: str = ""


ARCHETYPES = {a.id: a for a in (
    Archetype("benchmark_250", "Benchmark street (Round 1): 99 homes, 250 kVA, Rabbit", "rabbit", 1.0, 250.0, 99,
              BENCHMARK_X_OHM_PER_KM, "Unchanged from Round 1 so earlier results stay comparable."),
    Archetype("urban_short_160", "Urban short feeder: 80 homes, 160 kVA, Dog", "dog", 0.6, 160.0, 80),
    Archetype("suburban_100", "Suburban feeder: 70 homes, 100 kVA, Racoon", "racoon", 1.0, 100.0, 70),
    Archetype("rural_long_100", "Rural long feeder: 60 homes, 100 kVA, Rabbit", "rabbit", 1.5, 100.0, 60),
    Archetype("rural_weak_63", "Rural weak feeder: 40 homes, 63 kVA, Weasel", "weasel", 1.5, 63.0, 40,
              note="Smallest transformer in the plan range and a thin conductor."),
)}


def list_archetypes() -> list[dict]:
    return [{"id": a.id, "label": a.label, "conductor": a.conductor, "trafo_kva": a.trafo_kva, "n_homes": a.n_homes,
             "length_scale": a.length_scale, "x_ohm_per_km": a.x_ohm_per_km} for a in ARCHETYPES.values()]


def _nearest_homes(net: Network, n: int) -> np.ndarray:
    """Indices of the n homes electrically closest to the transformer (cumulative line length)."""
    g = nx.Graph()
    for a, b, length in zip(net.line_from, net.line_to, net.line_length_m):
        g.add_edge(int(a), int(b), weight=float(length))
    dist = nx.single_source_dijkstra_path_length(g, net.trafo.to_node, weight="weight")
    order = np.argsort([dist[int(node)] for node in net.house_node], kind="stable")
    return np.sort(order[:n])


def build(archetype_id: str, phases: str | np.ndarray = "random", seed: int = 42) -> Network:
    if archetype_id not in ARCHETYPES:
        raise KeyError(f"unknown archetype {archetype_id!r}; choose from {sorted(ARCHETYPES)}")
    a = ARCHETYPES[archetype_id]
    net = from_pandapower(build_grid(1.0), phases="round_robin", name=a.id)
    cond = CONDUCTORS[a.conductor]
    if archetype_id == "benchmark_250":
        keep = np.arange(net.n_homes)
    else:
        length_m = net.line_length_m * a.length_scale
        km = length_m / 1000
        lv_line = np.isin(net.line_from, net.lv_nodes) & np.isin(net.line_to, net.lv_nodes)
        r1 = np.where(lv_line, cond["r_ohm_per_km"] * km, net.line_r1_ohm * a.length_scale)
        x1 = np.where(lv_line, a.x_ohm_per_km * km, net.line_x1_ohm * a.length_scale)
        ratio = a.trafo_kva * 1000 / net.trafo.sn_va
        trafo = replace(net.trafo, sn_va=net.trafo.sn_va * ratio, pk_w=net.trafo.pk_w * ratio, p0_w=net.trafo.p0_w * ratio)
        net = net.replace(
            line_length_m=length_m, line_r1_ohm=r1, line_x1_ohm=x1, line_r0_ohm=r1 * ZERO_SEQUENCE_RATIO,
            line_x0_ohm=x1 * ZERO_SEQUENCE_RATIO, line_c1_f=net.line_c1_f * a.length_scale,
            line_i_n_a=np.where(lv_line, float(cond["i_a"]), net.line_i_n_a), trafo=trafo)
        keep = _nearest_homes(net, a.n_homes)
    phase = assign_phases(len(keep), phases, seed) if isinstance(phases, str) else np.asarray(phases, dtype=int)[keep]
    net = net.replace(house_node=net.house_node[keep], house_kwp=net.house_kwp[keep], house_phase=phase)
    return net.replace(provenance={
        **net.provenance,
        "archetype": a.id,
        "conductor": f"IS 398 Part II ACSR {a.conductor}: R {cond['r_ohm_per_km']} ohm/km at 20 C, {cond['i_a']} A at 75 C (verify against BIS copy)",
        "reactance": f"{a.x_ohm_per_km} ohm/km: " + ("Round 1 assumption" if archetype_id == "benchmark_250" else "estimate, not from the standard"),
        "topology": "benchmark: SimBench 1-LV-rural2 topology scaled in length; not a surveyed Indian feeder",
    })
