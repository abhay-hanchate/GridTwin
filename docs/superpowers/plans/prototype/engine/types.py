"""Canonical in-memory model shared by every v2 feature: network, scenarios, controls, results."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from engine.inverters import VoltVarCurve, VoltWattCurve

PHASES = ("A", "B", "C")


@dataclass(frozen=True)
class TrafoSpec:
    from_node: int
    to_node: int
    u1_v: float
    u2_v: float
    sn_va: float
    uk: float                 # relative short-circuit voltage (0.06 = 6%)
    pk_w: float
    i0: float                 # relative no-load current
    p0_w: float
    clock: int
    tap_min: int
    tap_max: int
    tap_nom: int
    tap_size_v: float         # volts per tap step on the HV side
    winding_from: str = "delta"
    winding_to: str = "wye_n"


@dataclass(frozen=True, eq=False)
class Network:
    name: str
    node_kv: np.ndarray                 # (N,) rated line-to-line kV
    lv_nodes: np.ndarray                # indices of LV nodes (< 1 kV)
    line_from: np.ndarray
    line_to: np.ndarray                 # (L,)
    line_r1_ohm: np.ndarray
    line_x1_ohm: np.ndarray
    line_r0_ohm: np.ndarray
    line_x0_ohm: np.ndarray
    line_c1_f: np.ndarray
    line_i_n_a: np.ndarray
    line_length_m: np.ndarray
    trafo: TrafoSpec
    source_node: int
    house_node: np.ndarray              # (H,) node index per home
    house_phase: np.ndarray             # (H,) 0, 1, 2 = A, B, C
    house_kwp: np.ndarray               # (H,) installed PV per home, 0 = none
    provenance: dict = field(default_factory=dict)
    node_xy: np.ndarray | None = None   # (N, 2) metres, for candidate tie switches
    conductor_alpha: float = 0.00403    # resistance temperature coefficient of aluminium per degree C (general knowledge, not sourced)
    conductor_delta_t_c: float = 10.0   # conductor temperature above ambient under load (assumption)

    @property
    def n_nodes(self) -> int:
        return len(self.node_kv)

    @property
    def n_homes(self) -> int:
        return len(self.house_node)

    @property
    def n_lines(self) -> int:
        return len(self.line_from)

    def replace(self, **changes) -> "Network":
        return replace(self, **changes)

    def with_phases(self, phases: np.ndarray) -> "Network":
        return replace(self, house_phase=np.asarray(phases, dtype=int))

    def with_pv(self, kwp: np.ndarray) -> "Network":
        return replace(self, house_kwp=np.asarray(kwp, dtype=float))

    def with_topology(self, add: list[dict] | None = None, remove: list[int] | None = None) -> "Network":
        """Copy with lines removed (by index) and lines added (dicts with from, to, r1, x1, r0, x0, c1, i_n)."""
        keep = np.ones(self.n_lines, dtype=bool)
        keep[list(remove or [])] = False
        cols = {"line_from": "from", "line_to": "to", "line_r1_ohm": "r1", "line_x1_ohm": "x1", "line_r0_ohm": "r0",
                "line_x0_ohm": "x0", "line_c1_f": "c1", "line_i_n_a": "i_n", "line_length_m": "length_m"}
        new = {name: np.r_[getattr(self, name)[keep], [a[key] for a in (add or [])]] for name, key in cols.items()}
        new["line_from"], new["line_to"] = new["line_from"].astype(int), new["line_to"].astype(int)
        return replace(self, **new)

    def is_radial(self) -> bool:
        """One connected tree over the LV nodes and the transformer's LV node (no loops, nothing islanded)."""
        import networkx as nx
        lv = set(self.lv_nodes.tolist())
        g = nx.Graph()
        g.add_nodes_from(lv)
        g.add_edges_from((int(a), int(b)) for a, b in zip(self.line_from, self.line_to) if a in lv and b in lv)
        return nx.is_connected(g) and g.number_of_edges() == g.number_of_nodes() - 1


@dataclass(frozen=True)
class BatterySpec:
    kw: float
    kwh: float
    node: int
    efficiency: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.90
    soc_start: float = 0.50


@dataclass(frozen=True, eq=False)
class DayScenarioBatch:
    t: pd.DatetimeIndex                 # (T,)
    load_kw: np.ndarray                 # (S, T, H)
    pv_per_kwp: np.ndarray              # (S, T)
    upstream_pu: np.ndarray             # (S, T)
    load_pf: float = 0.95
    labels: tuple = ()
    ambient_c: np.ndarray | None = None  # (S, T) air temperature; when given, line resistance is temperature-corrected

    @property
    def shape(self) -> tuple[int, int]:
        return self.pv_per_kwp.shape


@dataclass(frozen=True, eq=False)
class Controls:
    tap_pos: int = 0
    volt_var: VoltVarCurve | None = None
    volt_watt: VoltWattCurve | None = None
    pf_fixed: float | None = None
    export_limit_kw: np.ndarray | None = None      # (T, H) or (H,) maximum net export per home
    curtail_keep: float | None = None
    battery: BatterySpec | None = None
    inverter_s_factor: float = 1.0
    name: str = ""


@dataclass
class DayResult:
    t: pd.DatetimeIndex
    u_pu: np.ndarray                    # (S, T, Nlv, 3) phase-to-neutral, pu of 230 V
    line_loading_pct: np.ndarray        # (S, T, L)
    trafo_loading_pct: np.ndarray       # (S, T)
    trafo_p_kw: np.ndarray              # (S, T) into the HV side; negative = reverse flow
    losses_kw: np.ndarray               # (S, T)
    q_loss_kvar: np.ndarray             # (S, T)
    pv_kw: np.ndarray                   # (S, T) delivered
    pv_avail_kw: np.ndarray             # (S, T) available before any control
    inverter_kvar: np.ndarray           # (S, T) absorbed, positive = absorbing
    battery_kw: np.ndarray              # (S, T) positive = charging
    neutral_a: np.ndarray               # (S, T)
    vuf_pct: np.ndarray                 # (S, T)
    converged: np.ndarray               # (S, T) bool
    passes: int = 1                     # inverter-control passes used


@dataclass
class Violations:
    over: np.ndarray
    under: np.ndarray
    line: np.ndarray
    trafo: np.ndarray
    solver: np.ndarray                  # all (S, T) bool
    unbalance: np.ndarray               # (S, T) bool, only set when a voltage-unbalance limit is given
    unsafe: np.ndarray
    rule_id: str
