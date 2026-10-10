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


def write(root: Path, street: str, model, failure, guard: dict, train: Data, net: Network, *, extra: dict | None = None) -> Path:
    """Save the model and a manifest whose support box is the train split's min-max of every feature."""
    folder = Path(root) / street
    predict.save(folder / MODEL_FILE, model, failure)
    names = schema.feature_names(net.n_homes)
    mode_cols = train.x[:, -len(schema.MODES):]
    manifest = {
        "street": street, "model_kind": model.kind, "model_file": MODEL_FILE,
        "model_sha256": schema.file_sha256(folder / MODEL_FILE),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": "trained on simulated states: modelled scenario inputs labelled by the power-grid-model solver",
        "solver_hash": schema.solver_hash(), "street_hash": schema.street_hash(net),
        "feature_names": names, "n_homes": net.n_homes, "line_ends": schema.line_ends(net),
        "house_phase": net.house_phase.astype(int).tolist(), "default_pv_kwp": net.house_kwp.astype(float).tolist(),
        "battery_node": schema.battery_node(street), "battery_power_factor": 1.0, "home_power_factor": schema.LOAD_PF,
        "taps": sorted({int(t) for t in train.x[:, names.index("tap_pos")]}),
        "modes": [m for k, m in enumerate(schema.MODES) if (mode_cols[:, k] > 0.5).any()],
        "box": {"min": train.x.min(axis=0).tolist(), "max": train.x.max(axis=0).tolist()},
        # Round 3 (docs/DECISIONS.md): which homes have panels, and their sizes, must be a trained layout.
        "solar_layouts": np.unique(train.x[:, names.index("pv_kwp_0"):names.index("pv_kwp_0") + net.n_homes], axis=0).tolist(),
        "guard": guard, "failure_model": failure is not None, "failure_threshold": calibrate.FAILURE_THRESHOLD,
        "outputs": {"n_voltages": train.n_v, "n_lines": train.n_lines, "extremes": list(schema.EXTREMES)},
        "not_screened": ["voltage unbalance (VUF)", "neutral current", "reverse flow"],
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
