"""A6: bring a utility's own low-voltage feeder in from CSV files, validated with line-numbered errors.

Files (see docs/ONBOARDING.md):
  feeder.csv       node_id, parent_id, length_m, conductor        one row per line segment; the root's parent is "DT"
  homes.csv        home_id, node_id, phase, kwp                    phase A, B or C; kwp 0 for no solar
  transformer.csv  kva, uk_percent                                 one row
  meters.csv       timestamp, home_id, kwh, volts                  optional; checked for shape only
Every problem is collected (not just the first) and reported with its file and line number. Files are parsed by pandas
only, never executed, and are size-limited. Conductor data come from the IS 398 table in engine.archetypes;
reactance is the same estimate the archetypes use, and zero sequence is 3 x positive sequence (gate G5 range).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from engine.archetypes import CONDUCTORS, X_ESTIMATE_OHM_PER_KM, ZERO_SEQUENCE_RATIO
from engine.types import Network, TrafoSpec

MAX_BYTES = 10 * 1024 * 1024
ROOT_PARENT = "DT"
SCHEMAS = {"feeder": ["node_id", "parent_id", "length_m", "conductor"], "homes": ["home_id", "node_id", "phase", "kwp"],
           "transformer": ["kva", "uk_percent"], "meters": ["timestamp", "home_id", "kwh", "volts"]}
PHASES = {"A": 0, "B": 1, "C": 2}
HV_KV, LV_KV = 11.0, 0.4


class OnboardingError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__(f"{len(problems)} problem(s):\n" + "\n".join(problems))
        self.problems = problems


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)

    def add(self, file: str, line: int | None, message: str) -> None:
        self.problems.append(f"{file}.csv{f' line {line}' if line is not None else ''}: {message}")


def read_csv(path: Path, kind: str, report: Report) -> pd.DataFrame | None:
    if path.stat().st_size > MAX_BYTES:
        report.add(kind, None, f"file is larger than {MAX_BYTES // (1024 * 1024)} MB")
        return None
    df = pd.read_csv(path, dtype=str, skipinitialspace=True)
    missing = [c for c in SCHEMAS[kind] if c not in df.columns]
    if missing:
        report.add(kind, 1, f"missing column(s): {', '.join(missing)}")
        return None
    return df


def _number(df: pd.DataFrame, col: str, kind: str, report: Report, *, minimum: float | None = None,
            positive: bool = False) -> pd.Series:
    values = pd.to_numeric(df[col], errors="coerce")
    for i in np.flatnonzero(values.isna().to_numpy()):
        report.add(kind, i + 2, f"{col} is not a number: {df[col].iloc[i]!r}")
    if positive:
        for i in np.flatnonzero((values <= 0).to_numpy()):
            report.add(kind, i + 2, f"{col} must be positive")
    if minimum is not None:
        for i in np.flatnonzero((values < minimum).to_numpy()):
            report.add(kind, i + 2, f"{col} must be at least {minimum:g}")
    return values


def validate(feeder: pd.DataFrame, homes: pd.DataFrame, transformer: pd.DataFrame, report: Report) -> None:
    lengths = _number(feeder, "length_m", "feeder", report, positive=True)
    del lengths
    for i, c in enumerate(feeder["conductor"].str.strip().str.lower()):
        if c not in CONDUCTORS:
            report.add("feeder", i + 2, f"unknown conductor {c!r}; known: {', '.join(sorted(CONDUCTORS))}")
    dupes = feeder["node_id"][feeder["node_id"].duplicated()]
    for i in dupes.index:
        report.add("feeder", i + 2, f"node {feeder['node_id'][i]!r} appears twice")
    nodes = set(feeder["node_id"])
    for i, parent in enumerate(feeder["parent_id"]):
        if parent != ROOT_PARENT and parent not in nodes:
            report.add("feeder", i + 2, f"parent {parent!r} is not a node in the file")
    roots = (feeder["parent_id"] == ROOT_PARENT).sum()
    if roots != 1:
        report.add("feeder", None, f"exactly one segment must start at the transformer (parent_id {ROOT_PARENT}); found {roots}")
    g = nx.Graph()
    g.add_nodes_from(nodes | {ROOT_PARENT})
    g.add_edges_from(zip(feeder["parent_id"], feeder["node_id"]))
    if not nx.is_forest(g):
        cycle = nx.find_cycle(g)
        report.add("feeder", None, f"the feeder has a loop through {' - '.join(a for a, _ in cycle)}")
    elif not nx.is_connected(g):
        islanded = sorted(n for n in nodes if not nx.has_path(g, n, ROOT_PARENT))
        report.add("feeder", None, f"node(s) not connected to the transformer: {', '.join(islanded)}")
    for i, (node, phase) in enumerate(zip(homes["node_id"], homes["phase"].str.strip().str.upper())):
        if node not in nodes:
            report.add("homes", i + 2, f"node {node!r} is not in feeder.csv")
        if phase not in PHASES:
            report.add("homes", i + 2, f"phase must be A, B or C, got {phase!r}")
    _number(homes, "kwp", "homes", report, minimum=0)
    if len(transformer) != 1:
        report.add("transformer", None, f"expected one row, found {len(transformer)}")
    _number(transformer, "kva", "transformer", report, positive=True)
    _number(transformer, "uk_percent", "transformer", report, positive=True)


def build_network(feeder: pd.DataFrame, homes: pd.DataFrame, transformer: pd.DataFrame, name: str = "utility_feeder") -> Network:
    lv_ids = list(feeder["node_id"])
    index = {ROOT_PARENT: 1, **{n: i + 2 for i, n in enumerate(lv_ids)}}         # 0 = 11 kV source, 1 = DT LV bus
    km = pd.to_numeric(feeder["length_m"]).to_numpy() / 1000
    cond = [CONDUCTORS[c.strip().lower()] for c in feeder["conductor"]]
    r1 = np.array([c["r_ohm_per_km"] for c in cond]) * km
    x1 = X_ESTIMATE_OHM_PER_KM * km
    kva, uk = float(transformer["kva"].iloc[0]), float(transformer["uk_percent"].iloc[0]) / 100
    sn = kva * 1000
    trafo = TrafoSpec(from_node=0, to_node=1, u1_v=HV_KV * 1000, u2_v=LV_KV * 1000, sn_va=sn, uk=uk, pk_w=0.012 * sn,
                      i0=0.01, p0_w=0.0025 * sn, clock=5, tap_min=-2, tap_max=2, tap_nom=0, tap_size_v=0.025 * HV_KV * 1000)
    return Network(
        name=name, node_kv=np.r_[HV_KV, LV_KV, np.full(len(lv_ids), LV_KV)], lv_nodes=np.arange(1, len(lv_ids) + 2),
        line_from=np.array([index[p] for p in feeder["parent_id"]]), line_to=np.array([index[n] for n in lv_ids]),
        line_r1_ohm=r1, line_x1_ohm=x1, line_r0_ohm=r1 * ZERO_SEQUENCE_RATIO, line_x0_ohm=x1 * ZERO_SEQUENCE_RATIO,
        line_c1_f=np.zeros(len(lv_ids)), line_i_n_a=np.array([float(c["i_a"]) for c in cond]),
        line_length_m=km * 1000, trafo=trafo, source_node=0,
        house_node=np.array([index[n] for n in homes["node_id"]]),
        house_phase=np.array([PHASES[p.strip().upper()] for p in homes["phase"]]),
        house_kwp=pd.to_numeric(homes["kwp"]).to_numpy(float),
        provenance={"topology": "observed: utility feeder files", "conductor": "IS 398 Part II (1996) table",
                    "reactance": f"{X_ESTIMATE_OHM_PER_KM} ohm/km estimate", "transformer": "losses assumed (1.2% copper, 0.25% iron)",
                    "zero_sequence": f"assumed {ZERO_SEQUENCE_RATIO} x positive sequence (unsourced)"})


def load_feeder(folder: Path) -> Network:
    """Read and validate the files in `folder`; raise OnboardingError listing every problem."""
    report = Report()
    frames = {}
    for kind in ("feeder", "homes", "transformer"):
        path = folder / f"{kind}.csv"
        if not path.is_file():
            report.add(kind, None, "file is missing")
            continue
        frames[kind] = read_csv(path, kind, report)
    if (folder / "meters.csv").is_file():
        meters = read_csv(folder / "meters.csv", "meters", report)
        if meters is not None:
            _number(meters, "kwh", "meters", report, minimum=0)
            times = pd.to_datetime(meters["timestamp"], errors="coerce")
            for i in np.flatnonzero(times.isna().to_numpy()):
                report.add("meters", i + 2, f"timestamp is not a date and time: {meters['timestamp'].iloc[i]!r}")
    if all(frames.get(k) is not None for k in ("feeder", "homes", "transformer")):
        validate(frames["feeder"], frames["homes"], frames["transformer"], report)
    if report.problems:
        raise OnboardingError(report.problems)
    net = build_network(frames["feeder"], frames["homes"], frames["transformer"], name=folder.name)
    if not net.is_radial():
        raise OnboardingError(["feeder.csv: the network is not one radial tree"])
    return net
