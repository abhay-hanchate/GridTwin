"""The screening contract with Addition 1 (control): batched, CPU, and never a verdict.

A Screen is a prediction. Only the physical solver may call anything safe. Anything the artifact was not trained on
(another street, a line layout beyond the trained ones, a moved phase, an ambient correction, an unknown inverter mode,
a battery at an untrained node, a tap or an input outside the trained range, a state unlike the training states,
non-finite numbers) comes back "unsupported" and risky, with the reason, so the caller sends it to the solver.

Agreed additions to the original contract (all optional, so existing calls keep working):
- 10 Oct 2026: `screen(states, rule=...)`, and `house_phase`, `pv_kwp` and `ambient_c` on OperatingState.
- Round 4: `screen(..., vuf_limit=...)`; Screen also carries `vuf_pct`, `neutral_a` and `trafo_p_kw` (guarded;
  negative transformer power = reverse flow); the first three switched layouts of each street are supported.
Conventions: the battery is three-phase balanced at unity power factor; homes are at power factor 0.95;
"fixed_pf" is unity power factor; under Volt/Watt, `pv_kw` is the solar before the Volt/Watt cut; `pv_kwp=None` means
the street as built.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from engine.rules import VoltageRule, get_rule
from ml.surrogate import calibrate, predict, schema
from ml.surrogate.artifact import MANIFEST_FILE, MODEL_DIR

log = logging.getLogger("gridtwin.surrogate")
nan = math.nan


@dataclass(frozen=True, eq=False)
class OperatingState:            # one power-flow input: one street, one quarter-hour
    network_id: str              # an engine.archetypes id
    line_ends: tuple[tuple[int, int], ...]   # the topology actually used (switching changes it)
    load_kw: np.ndarray          # (H,) active demand per home
    pv_kw: np.ndarray            # (H,) delivered solar per home, after curtailment/export limits
    upstream_pu: float           # grid voltage at the transformer
    battery_kw: float = 0.0      # signed, + charging, three-phase balanced; 0 when no battery
    battery_node: int | None = None
    tap_pos: int = 0
    inverter_mode: str = "fixed_pf"   # or "volt_var", "volt_watt", "volt_var_watt"
    house_phase: tuple[int, ...] | None = None   # None: the street's phase map as built
    pv_kwp: np.ndarray | None = None             # (H,) inverter ratings; None: the street as built
    ambient_c: float | None = None               # an ambient correction is not supported: must be None


@dataclass(frozen=True)
class Screen:
    status: str                  # "supported" | "unsupported" (reason in `reason`)
    reason: str = ""
    v_max_pu: float = nan        # predicted, with the calibrated guard band applied
    v_min_pu: float = nan
    max_line_loading_pct: float = nan
    max_trafo_loading_pct: float = nan
    risky: bool = True           # conservative: True whenever unsupported or uncertain
    vuf_pct: float = nan         # round 4: worst voltage unbalance, guarded upward
    neutral_a: float = nan       # neutral current at the transformer, guarded upward
    trafo_p_kw: float = nan      # transformer power, guarded downward (negative: reverse flow possible)


@lru_cache(maxsize=8)
def _street_hash(street: str) -> str:
    from engine.archetypes import build
    return schema.street_hash(build(street, phases="round_robin"))       # what backend.v2.compute.network builds


def _ends(line_ends) -> tuple:
    return tuple(tuple(int(v) for v in e) for e in line_ends)


class StreetModel:
    def __init__(self, street: str, manifest: dict, model, failure, novelty):
        self.street, self.manifest, self.model, self.failure, self.novelty = street, manifest, model, failure, novelty
        self.n_homes = int(manifest["n_homes"])
        self.layouts = {_ends(ends): int(k) for ends, k in zip(manifest["line_layouts"], manifest["line_layout_index"])}
        self.house_phase = tuple(int(p) for p in manifest["house_phase"])
        self.default_kwp = np.asarray(manifest["default_pv_kwp"], float)
        self.battery_nodes = [int(n) for n in manifest["battery_nodes"]]
        self.box_min, self.box_max = np.asarray(manifest["box"]["min"]), np.asarray(manifest["box"]["max"])
        self.names = manifest["feature_names"]
        self.guard = manifest["guard"]
        self._street_ok: bool | None = None

    def street_ok(self) -> bool:
        if self._street_ok is None:
            self._street_ok = _street_hash(self.street) == self.manifest["street_hash"]
            if not self._street_ok:
                log.warning("surrogate for %s disabled: the street definition changed since training", self.street)
        return self._street_ok

    def check(self, s: OperatingState) -> tuple[str, np.ndarray | None]:
        """('', features) when supported, else (reason, None)."""
        m = self.manifest
        layout = self.layouts.get(_ends(s.line_ends))
        if layout is None:
            return "the line layout is not one the screen was trained on (switching beyond the trained layouts)", None
        if s.house_phase is not None and tuple(int(p) for p in s.house_phase) != self.house_phase:
            return "the phase map differs from the trained street", None
        if s.ambient_c is not None:
            return "an ambient temperature correction was not trained", None
        if s.inverter_mode not in m["modes"]:
            return f"inverter mode {s.inverter_mode!r} is not supported (trained: {', '.join(m['modes'])})", None
        slot = -1
        if s.battery_kw != 0:
            if s.battery_node not in self.battery_nodes:
                return f"a battery at node {s.battery_node} was not trained (trained nodes: {self.battery_nodes})", None
            slot = self.battery_nodes.index(int(s.battery_node))
        if int(s.tap_pos) not in m["taps"] or int(s.tap_pos) != s.tap_pos:
            return f"tap {s.tap_pos} was not trained (trained: {m['taps']})", None
        kwp = self.default_kwp if s.pv_kwp is None else np.asarray(s.pv_kwp, float)
        load, pv = np.asarray(s.load_kw, float), np.asarray(s.pv_kw, float)
        if not (load.shape == pv.shape == kwp.shape == (self.n_homes,)):
            return f"expected {self.n_homes} homes", None
        x = schema.features(load[None], pv[None], kwp[None], [s.upstream_pu], [s.tap_pos], [s.battery_kw], [slot],
                            [schema.MODES.index(s.inverter_mode)], [layout], len(self.battery_nodes))[0]
        if not np.isfinite(x).all():
            return "inputs must be finite", None
        if np.any(pv > kwp + 1e-6):
            return "delivered solar exceeds the installed kWp", None
        bad = np.flatnonzero((x < self.box_min - 1e-9) | (x > self.box_max + 1e-9))
        if len(bad):
            k = bad[0]
            return (f"{self.names[k]} = {x[k]:.4g} is outside the trained range {self.box_min[k]:.4g} to "
                    f"{self.box_max[k]:.4g}"), None
        if self.novelty is not None:
            d = float(self.novelty.distance(x[None])[0])
            if d > self.novelty.threshold:
                return f"the state is unlike the training states (novelty {d:.3g} above {self.novelty.threshold:.3g})", None
        return "", x


class Screener:
    def __init__(self, models: dict[str, StreetModel]):
        self.models = models

    @property
    def streets(self) -> list[str]:
        return sorted(self.models)

    def screen_detail(self, states: Sequence[OperatingState], rule: str | VoltageRule = "up_2005",
                      vuf_limit: float | None = None) -> dict:
        """Arrays for evaluation: supported, reason, point / guarded / optimistic outputs, risky, clearly_unsafe."""
        r = get_rule(rule) if isinstance(rule, str) else rule
        n, k_out = len(states), len(schema.EXTREMES + schema.EXTRAS)
        out = {"supported": np.zeros(n, bool), "reason": [""] * n, "point": np.full((n, k_out), nan),
               "guarded": np.full((n, k_out), nan), "optimistic": np.full((n, k_out), nan), "risky": np.ones(n, bool),
               "clearly_unsafe": np.zeros(n, bool), "p_fail": np.full(n, nan)}
        rows: dict[str, list[tuple[int, np.ndarray]]] = {}
        for i, s in enumerate(states):
            sm = self.models.get(s.network_id)
            if sm is None:
                out["reason"][i] = f"no surrogate for street {s.network_id!r} (trained: {', '.join(self.streets)})"
                continue
            if not sm.street_ok():
                out["reason"][i] = "the street definition changed since training"
                continue
            reason, x = sm.check(s)
            if reason:
                out["reason"][i] = reason
                continue
            rows.setdefault(s.network_id, []).append((i, x))
        for street, items in rows.items():
            sm = self.models[street]
            idx = np.array([i for i, _ in items])
            x = np.stack([x for _, x in items])
            pred = sm.model.outputs(x)
            p_fail = sm.failure.proba(x) if sm.failure is not None else None
            d = calibrate.decide(pred, sm.guard, r.vmin_pu, r.vmax_pu, p_fail, sm.manifest["failure_threshold"], vuf_limit)
            finite = np.isfinite(pred).all(axis=1)
            for j, i in enumerate(idx):
                if not finite[j]:
                    out["reason"][i] = "the model returned a non-finite prediction"
                    continue
                out["supported"][i] = True
                out["point"][i], out["guarded"][i], out["optimistic"][i] = pred[j], d["guarded"][j], d["optimistic"][j]
                out["risky"][i], out["clearly_unsafe"][i] = bool(d["risky"][j]), bool(d["clearly_unsafe"][j])
                if p_fail is not None:
                    out["p_fail"][i] = p_fail[j]
        return out

    def screen(self, states: Sequence[OperatingState], rule: str | VoltageRule = "up_2005",
               vuf_limit: float | None = None) -> list[Screen]:
        d = self.screen_detail(states, rule, vuf_limit)
        result = []
        for i in range(len(states)):
            if not d["supported"][i]:
                result.append(Screen("unsupported", d["reason"][i]))
                continue
            g = [float(v) for v in d["guarded"][i]]
            result.append(Screen("supported", "", g[0], g[1], g[2], g[3], bool(d["risky"][i]), g[4], g[5], g[6]))
        return result


def load_screener(model_dir: Path | None = None) -> Screener | None:
    """Every street artifact that passes its checks, or None (with a logged reason) when none does."""
    root = Path(model_dir) if model_dir is not None else MODEL_DIR
    manifests = sorted(root.glob(f"*/{MANIFEST_FILE}")) if root.is_dir() else []
    if not manifests:
        log.warning("no surrogate artifact in %s: physical-only evaluation", root)
        return None
    solver = schema.solver_hash()
    models = {}
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        street, model_path = manifest["street"], path.parent / manifest["model_file"]
        if manifest.get("round") != 4:
            log.warning("surrogate for %s refused: an artifact from an earlier round", street)
            continue
        if not model_path.is_file() or schema.file_sha256(model_path) != manifest["model_sha256"]:
            log.warning("surrogate for %s refused: model file missing or sha256 mismatch", street)
            continue
        if manifest["solver_hash"] != solver:
            log.warning("surrogate for %s refused: the solver code changed since training", street)
            continue
        model, failure, novelty = predict.load(model_path)
        models[street] = StreetModel(street, manifest, model, failure, novelty)
    if not models:
        log.warning("no usable surrogate artifact in %s: physical-only evaluation", root)
        return None
    return Screener(models)
