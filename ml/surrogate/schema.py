"""Feature order, supported streets and the hashes that tie a surrogate to the street and solver it was trained on."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np

from engine.types import Network

ROOT = Path(__file__).resolve().parents[2]
MODES = ("fixed_pf", "volt_var", "volt_watt", "volt_var_watt")
# Every node that was the street's highest-voltage node (engine.fixes.catalog.worst_node) on any of 24 sampled days of
# 2025, the 5th and 20th of each month (checked 10 Oct 2026). The controller puts its battery there by default.
BATTERY_NODES = {
    "benchmark_250": (21, 26, 54, 65),
    "urban_short_160": (13, 21, 26, 58, 62, 65),
    "suburban_100": (25, 26, 31, 58, 65, 69),
    "rural_long_100": (26, 58, 62, 65, 91),
    "rural_weak_63": (26, 31, 41, 58, 65, 69),
}
STREETS = tuple(BATTERY_NODES)
N_SWITCHED = 3                      # the first switching candidates, the ones the controller permits
LOAD_PF = 0.95                      # homes, as in every scenario batch
EXTREMES = ("v_max_pu", "v_min_pu", "max_line_loading_pct", "max_trafo_loading_pct")
EXTRAS = ("vuf_pct", "neutral_a", "trafo_p_kw")
SOLVER_FILES = ("engine/solver.py", "engine/inverters.py", "engine/fixes/switching.py")


def battery_nodes(network_id: str) -> tuple[int, ...]:
    return BATTERY_NODES[network_id]


def topologies(net: Network) -> list[Network]:
    """The street as built, then its first N_SWITCHED switched layouts (engine.fixes.switching)."""
    return list(_topologies(net))


@lru_cache(maxsize=16)
def _topologies(net: Network) -> tuple:                 # Network hashes by identity, so each object is built once
    from engine.fixes import switching
    return (net, *(switching.apply(net, rec) for rec in switching.candidates(net)[:N_SWITCHED]))


def feature_names(n_homes: int, n_battery_nodes: int) -> list[str]:
    return ([f"load_kw_{i}" for i in range(n_homes)] + [f"pv_kw_{i}" for i in range(n_homes)]
            + [f"pv_kwp_{i}" for i in range(n_homes)] + ["upstream_pu", "tap_pos"]
            + [f"battery_kw_at_{k}" for k in range(n_battery_nodes)]
            + [f"mode_{m}" for m in MODES] + [f"layout_{k}" for k in range(1 + N_SWITCHED)])


def features(load_kw, pv_kw, pv_kwp, upstream_pu, tap_pos, battery_kw, battery_slot, mode, topology,
             n_battery_nodes: int) -> np.ndarray:
    """(B, F) in the order of `feature_names`. `battery_slot` indexes the street's battery nodes (-1: no battery);
    `mode` indexes MODES; `topology` indexes `topologies` (0 = as built)."""
    b = len(upstream_pu)
    bat = np.zeros((b, n_battery_nodes))
    slot = np.asarray(battery_slot, int)
    on = slot >= 0
    bat[np.flatnonzero(on), slot[on]] = np.asarray(battery_kw, float)[on]
    return np.hstack([np.asarray(load_kw, float), np.asarray(pv_kw, float), np.asarray(pv_kwp, float),
                      np.asarray(upstream_pu, float).reshape(b, 1), np.asarray(tap_pos, float).reshape(b, 1), bat,
                      np.eye(len(MODES))[np.asarray(mode, int)], np.eye(1 + N_SWITCHED)[np.asarray(topology, int)]])


def _digest(parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(np.ascontiguousarray(p).tobytes() if isinstance(p, np.ndarray) else str(p).encode())
    return h.hexdigest()[:16]


def street_hash(net: Network) -> str:
    """Everything electrical about the street except the solar sizes (those are an input)."""
    t = net.trafo
    return _digest([net.node_kv, net.lv_nodes, net.line_from, net.line_to, net.line_r1_ohm, net.line_x1_ohm,
                    net.line_r0_ohm, net.line_x0_ohm, net.line_c1_f, net.line_i_n_a, net.house_node, net.house_phase,
                    t.u1_v, t.u2_v, t.sn_va, t.uk, t.pk_w, t.i0, t.p0_w, t.tap_size_v, net.source_node])


def line_ends(net: Network) -> list[list[int]]:
    return [[int(a), int(b)] for a, b in zip(net.line_from, net.line_to)]


def solver_hash(root: Path = ROOT) -> str:
    """The solver code the labels came from; line endings normalised so Windows and Linux agree."""
    h = hashlib.sha256()
    for rel in SOLVER_FILES:
        h.update(rel.encode())
        h.update((root / rel).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
