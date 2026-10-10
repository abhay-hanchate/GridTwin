"""The pre-registered bake-off, round 4 (docs/DECISIONS.md, Addition 2): fit, calibrate and select on development data.

    python -m scripts.surrogate_train                   # all five streets; writes ml/models/surrogate/<street>/ and
    python -m scripts.surrogate_train --street suburban_100        # ml/reports/surrogate_bakeoff.json
This script never reads the test or out-of-range splits: scripts/surrogate_evaluate.py scores them once, afterwards.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ml.surrogate import artifact, calibrate, dataset, metrics, predict, schema, train

REPORT = schema.ROOT / "ml" / "reports" / "surrogate_bakeoff.json"
RULES = ("up_2005", "pm10")


def latency(model, x: np.ndarray, batch: int = 1024, reps: int = 5) -> float:
    """Median seconds per state for the model alone at `batch` (the full screener is timed in the evaluation)."""
    xb = x[:batch]
    model.outputs(xb)
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        model.outputs(xb)
        times.append(time.perf_counter() - t0)
    return float(np.median(times) / len(xb))


def score(model, failure, guard: dict, data: train.Data, split: dataset.Split) -> dict:
    """Selection metrics on one development split, both rules."""
    from engine.rules import get_rule
    pred = model.outputs(data.x)
    p_fail = failure.proba(data.x) if failure is not None else None
    elements = model.elements(data.x) if hasattr(model, "elements") else None
    out = {"regression": metrics.regression(pred, split.labels, elements, data.n_v), "rules": {}}
    for rid in RULES:
        r = get_rule(rid)
        d = calibrate.decide(pred, guard, r.vmin_pu, r.vmax_pu, p_fail)
        unsafe = metrics.truly_unsafe(split.labels, r.vmin_pu, r.vmax_pu)
        out["rules"][rid] = {"guarded": metrics.screening(d["risky"], unsafe),
                             "point": metrics.screening(d["point_unsafe"], unsafe),
                             "boundary_guarded": metrics.screening(d["risky"][split.boundary], unsafe[split.boundary])}
    return out


def run_street(street: str, root: Path, model_root: Path, seed: int) -> dict:
    from backend.v2 import compute
    t0 = time.perf_counter()
    sp = {s: dataset.load_split(street, s, root) for s in ("train", "tune", "calibrate")}
    data = {s: train.prepare(v, street) for s, v in sp.items()}
    print(f"{street}: loaded {[len(v) for v in sp.values()]} states in {time.perf_counter() - t0:.0f} s", flush=True)
    failure, failure_info = train.fit_failure(data["train"], data["tune"])
    novelty = train.fit_novelty(data["train"], data["calibrate"])
    fitted = {}
    for kind, fit in (("ridge", train.fit_ridge), ("lgbm", train.fit_lgbm), ("mlp", lambda a, b: train.fit_mlp(a, b, seed=seed))):
        t = time.perf_counter()
        fitted[kind] = (*fit(data["train"], data["tune"]), time.perf_counter() - t)
        print(f"{street}: {kind} in {fitted[kind][2]:.0f} s", flush=True)
    candidate_dir = model_root / "candidates" / street
    candidates, selection_scores = {}, {}
    for kind, (model, info, seconds) in fitted.items():
        guard = train.guard(model, data["calibrate"])
        tune_score = score(model, failure, guard, data["tune"], sp["tune"])
        fs = sum(tune_score["rules"][r]["guarded"]["unsafe_as_safe"] for r in RULES)
        fr = float(np.mean([tune_score["rules"][r]["guarded"]["false_rejection_rate"] or 0.0 for r in RULES]))
        selection_scores[kind] = {"false_safe": fs, "false_rejection_rate": round(fr, 5), "latency_s": latency(model, data["tune"].x)}
        info = {k: v for k, v in info.items() if k != "history"} | ({"tune_history": info["history"]} if "history" in info else {})
        candidates[kind] = {"model": model, "guard": guard, "report": {
            "fit_seconds": round(seconds, 1), "fit": info,
            "guard": {"at_limits": calibrate.limit_margins(guard), "edges": guard["edges"], "bin_counts": guard["bin_counts"],
                      "level": guard["level"], "n": guard["n"]},
            "tune": tune_score, "selection": selection_scores[kind]}}
        predict.save(candidate_dir / f"{kind}.npz", model, failure, novelty)
        (candidate_dir / f"{kind}_guard.json").write_text(json.dumps(guard), encoding="utf-8")
    chosen, why = train.select(selection_scores)
    selected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{street}: selected {chosen} ({why})", flush=True)
    net = compute.network(street)
    artifact.write(model_root, street, candidates[chosen]["model"], failure, candidates[chosen]["guard"], data["train"], net,
                   novelty=novelty,
                   extra={"selected_at_utc": selected_at, "selection_reason": why, "training_seed": seed,
                          "dataset_manifest_sha256": schema.file_sha256(dataset.street_dir(street, root) / "manifest.json"),
                          "trained_on": {s: len(v) for s, v in sp.items()}})
    supported_cal = float((novelty.distance(data["calibrate"].x) <= novelty.threshold).mean())
    return {"round": 4, "selected": chosen, "reason": why, "selected_at_utc": selected_at, "failure_model": failure_info,
            "novelty": {"components": int(len(novelty.variances)), "threshold": novelty.threshold,
                        "calibrate_share_inside": round(supported_cal, 5)},
            "states": {s: {"total": len(v), "boundary": int(v.boundary.sum()), "solver_failures": int((~v.labels.converged).sum())}
                       for s, v in sp.items()},
            "candidates": {k: v["report"] for k, v in candidates.items()}, "seconds": round(time.perf_counter() - t0, 1)}


def main(argv=None) -> None:
    warnings.filterwarnings("ignore")
    p = argparse.ArgumentParser()
    p.add_argument("--street", action="append", choices=schema.STREETS)
    p.add_argument("--root", default=str(dataset.DATA_DIR))
    p.add_argument("--models", default=str(artifact.MODEL_DIR))
    p.add_argument("--report", default=str(REPORT))
    p.add_argument("--seed", type=int, default=train.SEED)
    args = p.parse_args(argv)
    report_path = Path(args.report)
    for street in args.street or schema.STREETS:
        result = run_street(street, Path(args.root), Path(args.models), args.seed)
        # Re-read before writing: several streets may train in parallel processes.
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        report.update({"pre_registration": "docs/DECISIONS.md, 'Addition 2', round 4",
                       "provenance": "simulated states labelled by the power-grid-model solver; selection on tune only",
                       "rules": RULES})
        report.setdefault("streets", {})[street] = result
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
