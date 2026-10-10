"""Generate the surrogate's solver-labelled states (Addition 2, requirement 2.1).

    python -m scripts.surrogate_generate                      # both streets, all families, then the out-of-range sets
    python -m scripts.surrogate_generate --pilot              # two families per split, two scenarios: timing check

Resumable: a family whose file exists is skipped. Writes data/surrogate/<street>/families/*.npz (git-ignored),
data/surrogate/<street>/ood.npz (git-ignored), data/surrogate/<street>/manifest.json and data/surrogate/splits.json.
Every state is simulated: modelled scenario inputs labelled by the power-grid-model solver.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np

from ml.surrogate import dataset, generate, schema

STREETS = tuple(schema.BATTERY_NODES)
OOD_SEED = 20261010


def _run(fam: dict, n_scenarios: int, boundary_share: float, root: str) -> dict:
    warnings.filterwarnings("ignore")
    from pathlib import Path

    from backend.v2 import compute
    fam = generate.Family(**fam)
    path = dataset.street_dir(fam.street, Path(root)) / "families" / f"{fam.id}.npz"
    if path.exists():
        with np.load(path) as d:
            return _row(fam, d["boundary"], d["l_converged"], float(d["seconds"]))
    t0 = time.perf_counter()
    out = generate.run_family(compute.network(fam.street), fam, n_scenarios=n_scenarios, boundary_share=boundary_share)
    seconds = time.perf_counter() - t0
    dataset.save_family(path, out, seconds)
    return _row(fam, out["boundary"], out["labels"].converged, seconds)


def _row(fam, boundary, converged, seconds) -> dict:
    return {**asdict(fam), "states": int(len(boundary)), "boundary_states": int(boundary.sum()),
            "solver_failures": int((~converged.astype(bool)).sum()), "seconds": round(seconds, 2)}


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--street", action="append", choices=STREETS)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--root", default=str(dataset.DATA_DIR))
    args = p.parse_args(argv)
    from pathlib import Path
    root = Path(args.root)
    n_scn = 2 if args.pilot else generate.N_SCENARIOS
    splits_doc = {"definition": {
        "dev_months": generate.DEV_MONTHS, "dev_days": generate.DEV_DAYS, "tune_months": generate.TUNE_MONTHS,
        "calibrate_months": generate.CALIBRATE_MONTHS, "test_months": generate.TEST_MONTHS, "test_days": generate.TEST_DAYS,
        "adoption_dev": generate.ADOPTION_DEV, "adoption_test": generate.ADOPTION_TEST,
        "held_out_tap_mode": sorted(generate.HELD_OUT), "families_per_date": generate.FAMILIES_PER_DATE,
        "scenarios_per_family": n_scn, "boundary_share": generate.BOUNDARY_SHARE, "ood_kinds": generate.OOD_KINDS,
        "rule": "split by family (date, adoption, tap, mode), never by row or seed"}, "streets": {}}
    for street in args.street or STREETS:
        fams = generate.families(street)
        if args.pilot:
            fams = [f for s in generate.SPLITS for f in [x for x in fams if x.split == s][:2]]
        t0 = time.perf_counter()
        rows = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(_run, asdict(f), n_scn, generate.BOUNDARY_SHARE, str(root)) for f in fams]
            for i, job in enumerate(as_completed(jobs), 1):
                rows.append(job.result())
                print(f"{street}: {i}/{len(jobs)} families ({rows[-1]['id']}, {rows[-1]['seconds']} s)", flush=True)
        rows.sort(key=lambda r: r["id"])
        from backend.v2 import compute
        net = compute.network(street)
        _write_manifest(root, street, rows, net, n_scn, time.perf_counter() - t0, args.pilot)
        test = dataset.load_split(street, "test", root)
        base = test.states.take(np.flatnonzero(~test.boundary))
        t1 = time.perf_counter()
        ood = generate.out_of_range(net, street, base, np.random.default_rng(OOD_SEED), per_kind=40 if args.pilot else 250)
        dataset.save_ood(dataset.street_dir(street, root) / "ood.npz", ood)
        manifest_path = dataset.street_dir(street, root) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["ood"] = {"seed": OOD_SEED, "seconds": round(time.perf_counter() - t1, 1),
                           "kinds": {k: {"states": len(v["states"]), "solver_failures": int((~v["labels"].converged).sum())}
                                     for k, v in ood.items()}}
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        splits_doc["streets"][street] = {s: [r["id"] for r in rows if r["split"] == s] for s in generate.SPLITS}
        print(f"{street}: done in {time.perf_counter() - t0:.0f} s", flush=True)
        del test
    (root / ("splits_pilot.json" if args.pilot else "splits.json")).write_text(json.dumps(splits_doc, indent=1), encoding="utf-8")


def _write_manifest(root, street, rows, net, n_scn, seconds, pilot) -> None:
    import lightgbm
    import power_grid_model
    import sklearn
    per_split = Counter()
    for r in rows:
        for k in ("states", "boundary_states", "solver_failures"):
            per_split[(r["split"], k)] += r[k]
    manifest = {
        "street": street, "pilot": pilot, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": "simulated: app scenario generator inputs (modelled forecasts, CEEW-based demand analogs), "
                      "labels from the power-grid-model solver; not measured data",
        "solver": {"engine": "power-grid-model", "version": power_grid_model.__version__, "asymmetric": True,
                   "method": "newton_raphson", "tolerance": 1e-8, "max_iterations": 40, "solver_hash": schema.solver_hash(),
                   "inverter_passes_max": 80, "damping": 0.3},
        "street_hash": schema.street_hash(net), "battery_node": schema.battery_node(street),
        "home_power_factor": schema.LOAD_PF, "battery_power_factor": 1.0,
        "config": {"scenarios_per_family": n_scn, "battery_share": generate.BATTERY_SHARE, "battery_kw": generate.BATTERY_KW,
                   "curtail_share": generate.CURTAIL_SHARE, "keep_range": generate.KEEP_RANGE,
                   "boundary_share": generate.BOUNDARY_SHARE, "boundary_v": generate.BOUNDARY_V,
                   "boundary_loading": generate.BOUNDARY_LOADING, "upstream_bracket": generate.UPSTREAM_BRACKET,
                   "load_scale_bracket": generate.LOAD_SCALE_BRACKET, "illinois_steps": generate.ILLINOIS_STEPS},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "sklearn": sklearn.__version__,
                        "lightgbm": lightgbm.__version__, "machine": platform.processor()},
        "seconds": round(seconds, 1),
        "totals": {s: {k: per_split[(s, k)] for k in ("states", "boundary_states", "solver_failures")} for s in generate.SPLITS},
        "families": rows,
    }
    path = dataset.street_dir(street, root) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
