"""The pre-registered bake-off (docs/DECISIONS.md, Addition 2): fit, calibrate and select on development data only.

    python -m scripts.surrogate_train                  # both streets; writes ml/models/surrogate/<street>/ and
                                                       # ml/reports/surrogate_bakeoff.json
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
from ml.surrogate.metrics import NOMINAL_V

REPORT = schema.ROOT / "ml" / "reports" / "surrogate_bakeoff.json"
RULES = ("up_2005", "pm10")


def latency(model, x: np.ndarray, batch: int = 1024, reps: int = 5) -> float:
    """Median seconds per state for the model alone at `batch` (feature building and range checks are timed in the
    evaluation, on the full screener)."""
    xb = x[:batch]
    model.extremes(xb)
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        model.extremes(xb)
        times.append(time.perf_counter() - t0)
    return float(np.median(times) / len(xb))


def score(model, failure, guard: dict, data: train.Data, split: dataset.Split) -> dict:
    """Selection metrics on one development split, both rules."""
    from engine.rules import get_rule
    pred = model.extremes(data.x)
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


def guard_in_units(guard: dict) -> dict:
    """The danger margins at the limits (V and points), plus the raw table when the margin is one per extreme."""
    out = {"at_limits": calibrate.limit_margins(guard)}
    if "edges" not in guard:
        conv = np.array([NOMINAL_V, NOMINAL_V, 1.0, 1.0])
        out.update({side: [round(float(v) * c, 4) for v, c in zip(guard[side], conv)] for side in ("danger", "optimistic")})
    return out


def run_street(street: str, root: Path, model_root: Path, seed: int) -> dict:
    candidate_dir = model_root / "candidates" / street
    from backend.v2 import compute
    t0 = time.perf_counter()
    sp = {s: dataset.load_split(street, s, root) for s in ("train", "tune", "calibrate")}
    data = {s: train.prepare(v) for s, v in sp.items()}
    print(f"{street}: loaded {[len(v) for v in sp.values()]} states in {time.perf_counter() - t0:.0f} s", flush=True)
    failure, failure_info = train.fit_failure(data["train"], data["tune"])
    fitted = {}
    t = time.perf_counter()
    fitted["ridge"] = (*train.fit_ridge(data["train"], data["tune"]), time.perf_counter() - t)
    print(f"{street}: ridge alpha {fitted['ridge'][1]['alpha']} in {fitted['ridge'][2]:.0f} s", flush=True)
    t = time.perf_counter()
    fitted["lgbm"] = (*train.fit_lgbm(data["train"], data["tune"]), time.perf_counter() - t)
    print(f"{street}: lightgbm in {fitted['lgbm'][2]:.0f} s", flush=True)
    t = time.perf_counter()
    fitted["mlp"] = (*train.fit_mlp(data["train"], data["tune"], seed=seed), time.perf_counter() - t)
    print(f"{street}: mlp best epoch {fitted['mlp'][1]['best_epoch']} in {fitted['mlp'][2]:.0f} s", flush=True)

    cal = data["calibrate"]
    ok = cal.converged
    candidates, selection_scores = {}, {}
    for kind, (model, info, seconds) in fitted.items():
        guard = calibrate.fit_guard(model.extremes(cal.x[ok]), cal.extremes[ok])
        tune_score = score(model, failure, guard, data["tune"], sp["tune"])
        lat = latency(model, data["tune"].x)
        fs = sum(tune_score["rules"][r]["guarded"]["unsafe_as_safe"] for r in RULES)
        fr = float(np.mean([tune_score["rules"][r]["guarded"]["false_rejection_rate"] or 0.0 for r in RULES]))
        selection_scores[kind] = {"false_safe": fs, "false_rejection_rate": round(fr, 5), "latency_s": lat}
        info = {k: v for k, v in info.items() if k != "history"} | ({"tune_history": info["history"]} if "history" in info else {})
        candidates[kind] = {"model": model, "guard": guard, "report": {
            "fit_seconds": round(seconds, 1), "fit": info, "guard": {**guard_in_units(guard), "level": guard["level"], "n": guard["n"]},
            "tune": tune_score, "calibrate_regression": metrics.regression(model.extremes(cal.x), sp["calibrate"].labels),
            "selection": selection_scores[kind]}}
        predict.save(candidate_dir / f"{kind}.npz", model, failure)
        (candidate_dir / f"{kind}_guard.json").write_text(json.dumps(guard), encoding="utf-8")
    chosen, why = train.select(selection_scores)
    selected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{street}: selected {chosen} ({why})", flush=True)
    net = compute.network(street)
    data_manifest = dataset.street_dir(street, root) / "manifest.json"
    artifact.write(model_root, street, candidates[chosen]["model"], failure, candidates[chosen]["guard"], data["train"], net,
                   extra={"selected_at_utc": selected_at, "selection_reason": why, "guard_round": 1, "training_seed": seed,
                          "dataset_manifest_sha256": schema.file_sha256(data_manifest),
                          "trained_on": {s: len(v) for s, v in sp.items()}})
    return {"selected": chosen, "reason": why, "selected_at_utc": selected_at, "failure_model": failure_info,
            "states": {s: {"total": len(v), "boundary": int(v.boundary.sum()), "solver_failures": int((~v.labels.converged).sum())}
                       for s, v in sp.items()},
            "candidates": {k: v["report"] for k, v in candidates.items()}, "seconds": round(time.perf_counter() - t0, 1)}


def round2(street: str, root: Path, model_root: Path, report: dict, bins: int = 8) -> dict:
    """Pre-registered round 2 (docs/DECISIONS.md): the same fitted models, Mondrian margins by predicted value.
    Ships only if the model's guarded unsafe-as-safe on tune is not higher than in round 1."""
    from backend.v2 import compute
    first = report["streets"][street]
    sp = {s: dataset.load_split(street, s, root) for s in ("train", "tune", "calibrate")}
    data = {s: train.prepare(v) for s, v in sp.items()}
    cal, ok = data["calibrate"], data["calibrate"].converged
    candidate_dir = model_root / "candidates" / street
    scores, rows, kept = {}, {}, {}
    for kind in ("ridge", "lgbm", "mlp"):
        model, failure = predict.load(candidate_dir / f"{kind}.npz")
        guard = calibrate.fit_guard(model.extremes(cal.x[ok]), cal.extremes[ok], bins=bins)
        (candidate_dir / f"{kind}_guard_round2.json").write_text(json.dumps(guard), encoding="utf-8")
        tune_score = score(model, failure, guard, data["tune"], sp["tune"])
        fs = sum(tune_score["rules"][r]["guarded"]["unsafe_as_safe"] for r in RULES)
        fr = float(np.mean([tune_score["rules"][r]["guarded"]["false_rejection_rate"] or 0.0 for r in RULES]))
        scores[kind] = {"false_safe": fs, "false_rejection_rate": round(fr, 5), "latency_s": first["candidates"][kind]["selection"]["latency_s"]}
        rows[kind] = {"guard": {**guard_in_units(guard), "bins": bins, "bin_counts": guard["bin_counts"]}, "tune": tune_score,
                      "selection": scores[kind]}
        kept[kind] = (model, failure, guard)
    chosen, why = train.select(scores)
    first_fs = first["candidates"][chosen]["selection"]["false_safe"]
    ships = scores[chosen]["false_safe"] <= first_fs
    out = {"bins": bins, "selected": chosen, "reason": why, "ships": ships,
           "rule": "round 2 ships only if its tune unsafe-as-safe is not higher than round 1's for the same model",
           "selected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "candidates": rows}
    if ships:
        model, failure, guard = kept[chosen]
        net = compute.network(street)
        data_manifest = dataset.street_dir(street, root) / "manifest.json"
        artifact.write(model_root, street, model, failure, guard, data["train"], net,
                       extra={"selected_at_utc": out["selected_at_utc"], "selection_reason": f"round 2: {why}",
                              "guard_round": 2, "training_seed": train.SEED,
                              "dataset_manifest_sha256": schema.file_sha256(data_manifest),
                              "trained_on": {s: len(v) for s, v in sp.items()}})
    print(f"{street}: round 2 selected {chosen}; ships: {ships}", flush=True)
    return out


def main(argv=None) -> None:
    warnings.filterwarnings("ignore")
    p = argparse.ArgumentParser()
    p.add_argument("--street", action="append", choices=tuple(schema.BATTERY_NODES))
    p.add_argument("--root", default=str(dataset.DATA_DIR))
    p.add_argument("--models", default=str(artifact.MODEL_DIR))
    p.add_argument("--report", default=str(REPORT))
    p.add_argument("--seed", type=int, default=train.SEED)
    p.add_argument("--round2", action="store_true", help="recalibrate the fitted candidates with Mondrian margins")
    args = p.parse_args(argv)
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report.update({"pre_registration": "docs/DECISIONS.md, 'Addition 2: power-flow surrogate'",
                   "provenance": "simulated states labelled by the power-grid-model solver; selection on tune only",
                   "rules": RULES, "streets": report.get("streets", {})})
    for street in args.street or tuple(schema.BATTERY_NODES):
        if args.round2:
            report["streets"][street]["round2"] = round2(street, Path(args.root), Path(args.models), report)
        else:
            report["streets"][street] = run_street(street, Path(args.root), Path(args.models), args.seed)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
