"""A street's surrogate artifact: model.npz plus manifest.json declaring exactly what it supports (requirement 2.5)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine.types import Network
from ml.surrogate import calibrate, predict, schema
from ml.surrogate.train import Data

MODEL_DIR = schema.ROOT / "ml" / "models" / "surrogate"
MODEL_FILE, MANIFEST_FILE = "model.npz", "manifest.json"


def write(root: Path, street: str, model, failure, guard: dict, train: Data, net: Network, *,
          novelty: predict.Novelty | None = None, extra: dict | None = None) -> Path:
    """Save the model and a manifest whose support is the train split's min-max of every feature, the trained line
    layouts, battery nodes, taps and modes, and (round 4) a novelty threshold."""
    folder = Path(root) / street
    predict.save(folder / MODEL_FILE, model, failure, novelty)
    nodes = schema.battery_nodes(street)
    names = schema.feature_names(net.n_homes, len(nodes))
    mode_cols = train.x[:, train.mode_cols]
    layout_cols = train.x[:, -(1 + schema.N_SWITCHED):]
    layouts = schema.topologies(net)
    manifest = {
        "street": street, "round": 4, "model_kind": model.kind, "model_file": MODEL_FILE,
        "model_sha256": schema.file_sha256(folder / MODEL_FILE),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": "trained on simulated states: modelled scenario inputs labelled by the power-grid-model solver",
        "solver_hash": schema.solver_hash(), "street_hash": schema.street_hash(net),
        "feature_names": names, "n_homes": net.n_homes,
        "line_layouts": [schema.line_ends(t) for k, t in enumerate(layouts) if (layout_cols[:, k] > 0.5).any()],
        "line_layout_index": [k for k in range(len(layouts)) if (layout_cols[:, k] > 0.5).any()],
        "house_phase": net.house_phase.astype(int).tolist(), "default_pv_kwp": net.house_kwp.astype(float).tolist(),
        "battery_nodes": list(nodes), "battery_power_factor": 1.0, "home_power_factor": schema.LOAD_PF,
        "taps": sorted({int(t) for t in train.x[:, names.index("tap_pos")]}),
        "modes": [m for k, m in enumerate(schema.MODES) if (mode_cols[:, k] > 0.5).any()],
        "box": {"min": train.x.min(axis=0).tolist(), "max": train.x.max(axis=0).tolist()},
        "novelty": None if novelty is None else {"threshold": novelty.threshold, "components": int(len(novelty.variances))},
        "guard": guard, "failure_model": failure is not None, "failure_threshold": calibrate.FAILURE_THRESHOLD,
        "outputs": {"n_voltages": train.n_v, "n_lines": train.n_lines, "outputs": list(schema.EXTREMES + schema.EXTRAS)},
        "not_screened": ["moved phase maps", "switched layouts beyond the trained ones", "ambient temperature correction"],
        **(extra or {}),
    }
    (folder / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1, default=_json), encoding="utf-8")
    return folder


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))
