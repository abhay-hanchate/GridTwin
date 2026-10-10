"""Read and write generated states: one compressed file per family, one for the out-of-range sets, and a manifest."""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

from ml.surrogate.schema import ROOT
from ml.surrogate.teacher import Labels, StateArrays

DATA_DIR = ROOT / "data" / "surrogate"
LABEL_KEYS = ("u_pu", "line_loading_pct", "trafo_loading_pct", "converged", "passes")


def street_dir(street: str, root: Path = DATA_DIR) -> Path:
    return root / street


def _pack(prefix: str, states: StateArrays, labels: Labels) -> dict:
    out = {f"{prefix}s_{f.name}": getattr(states, f.name) for f in fields(StateArrays)}
    for k in LABEL_KEYS:
        v = getattr(labels, k)
        out[f"{prefix}l_{k}"] = v.astype(np.float32) if v.dtype.kind == "f" else v
    return out


def _unpack(data, prefix: str) -> tuple[StateArrays, Labels]:
    states = StateArrays(**{f.name: data[f"{prefix}s_{f.name}"] for f in fields(StateArrays)})
    labels = Labels(**{k: data[f"{prefix}l_{k}"].astype(float) if data[f"{prefix}l_{k}"].dtype.kind == "f"
                       else data[f"{prefix}l_{k}"] for k in LABEL_KEYS})
    return states, labels


def save_family(path: Path, out: dict, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, family=json.dumps(out["family"]), seconds=seconds, boundary=out["boundary"],
                        boundary_kind=out["boundary_kind"], step=out["step"], **_pack("", out["states"], out["labels"]))


def save_ood(path: Path, ood: dict) -> None:
    arrays = {}
    for kind, item in ood.items():
        arrays.update(_pack(f"{kind}__", item["states"], item["labels"]))
        arrays[f"{kind}__house_phase"] = item["network"].house_phase
        arrays[f"{kind}__line_from"] = item["network"].line_from
        arrays[f"{kind}__line_to"] = item["network"].line_to
        arrays[f"{kind}__battery_node"] = item["battery_node"]
    np.savez_compressed(path, kinds=json.dumps(list(ood)), **arrays)


@dataclass
class Split:
    states: StateArrays
    labels: Labels
    boundary: np.ndarray
    boundary_kind: np.ndarray
    family: np.ndarray          # family id per row
    step: np.ndarray

    def __len__(self) -> int:
        return len(self.boundary)

    def take(self, idx) -> "Split":
        lab = Labels(*(getattr(self.labels, k)[idx] for k in LABEL_KEYS))
        return Split(self.states.take(idx), lab, self.boundary[idx], self.boundary_kind[idx], self.family[idx],
                     self.step[idx])


def load_split(street: str, split: str, root: Path = DATA_DIR) -> Split:
    manifest = json.loads((street_dir(street, root) / "manifest.json").read_text(encoding="utf-8"))
    ids = [f["id"] for f in manifest["families"] if f["split"] == split]
    parts = []
    for fid in ids:
        with np.load(street_dir(street, root) / "families" / f"{fid}.npz") as d:
            s, lab = _unpack(d, "")
            parts.append(Split(s, lab, d["boundary"], d["boundary_kind"], np.full(len(d["boundary"]), fid), d["step"]))
    if not parts:
        raise FileNotFoundError(f"no families for {street}/{split}")
    return Split(StateArrays.concat([p.states for p in parts]),
                 Labels(*(np.concatenate([getattr(p.labels, k) for p in parts]) for k in LABEL_KEYS)),
                 np.concatenate([p.boundary for p in parts]), np.concatenate([p.boundary_kind for p in parts]),
                 np.concatenate([p.family for p in parts]), np.concatenate([p.step for p in parts]))


def load_ood(street: str, root: Path = DATA_DIR) -> dict:
    with np.load(street_dir(street, root) / "ood.npz") as d:
        out = {}
        for kind in json.loads(str(d["kinds"])):
            s, lab = _unpack(d, f"{kind}__")
            out[kind] = {"states": s, "labels": lab, "house_phase": d[f"{kind}__house_phase"],
                         "line_ends": np.stack([d[f"{kind}__line_from"], d[f"{kind}__line_to"]], axis=1),
                         "battery_node": int(d[f"{kind}__battery_node"])}
        return out
