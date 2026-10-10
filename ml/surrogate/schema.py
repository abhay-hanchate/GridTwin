"""Feature order, supported streets and the hashes that tie a surrogate to the street and solver it was trained on."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from engine.types import Network

ROOT = Path(__file__).resolve().parents[2]
MODES = ("fixed_pf", "volt_var", "volt_watt", "volt_var_watt")
# The street's highest-voltage node (engine.fixes.catalog.worst_node), the same in January, May, August and
# November 2025 (checked 10 Oct 2026). The controller puts its battery there by default.
BATTERY_NODES = {"benchmark_250": 65, "rural_weak_63": 26}
LOAD_PF = 0.95                      # homes, as in every scenario batch
EXTREMES = ("v_max_pu", "v_min_pu", "max_line_loading_pct", "max_trafo_loading_pct")
SOLVER_FILES = ("engine/solver.py", "engine/inverters.py")


def battery_node(network_id: str) -> int:
    return BATTERY_NODES[network_id]


def feature_names(n_homes: int) -> list[str]:
    return ([f"load_kw_{i}" for i in range(n_homes)] + [f"pv_kw_{i}" for i in range(n_homes)]
            + [f"pv_kwp_{i}" for i in range(n_homes)] + ["upstream_pu", "tap_pos", "battery_kw"]
            + [f"mode_{m}" for m in MODES])


def features(load_kw, pv_kw, pv_kwp, upstream_pu, tap_pos, battery_kw, mode) -> np.ndarray:
    """(B, 3H + 7) in the order of `feature_names`; `mode` is an index into MODES."""
    b = len(upstream_pu)
    onehot = np.eye(len(MODES))[np.asarray(mode, int)]
    return np.hstack([np.asarray(load_kw, float), np.asarray(pv_kw, float), np.asarray(pv_kwp, float),
                      np.asarray(upstream_pu, float).reshape(b, 1), np.asarray(tap_pos, float).reshape(b, 1),
                      np.asarray(battery_kw, float).reshape(b, 1), onehot])


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
