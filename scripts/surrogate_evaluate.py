"""Score the surrogate once on the held-out splits and measure it inside complete candidate evaluation (2.3, 2.5-2.8).

    python -m scripts.surrogate_evaluate              # both streets; run after scripts.surrogate_train
    python -m scripts.surrogate_evaluate --quick      # fewer dates and repetitions (a smoke run, not the evidence)

Writes ml/reports/surrogate_evaluation.json, ml/reports/surrogate_disagreements.json and a small committed sample of
test states per street (data/surrogate/<street>/sample.npz). Everything is simulated; every verdict is the solver's.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ml.surrogate import artifact, calibrate, dataset, generate, metrics, predict, schema, train
from ml.surrogate.api import OperatingState, load_screener
from ml.surrogate.teacher import StateArrays, solve_states

REPORT = schema.ROOT / "ml" / "reports" / "surrogate_evaluation.json"
DISAGREEMENTS = schema.ROOT / "ml" / "reports" / "surrogate_disagreements.json"
RULES = ("up_2005", "pm10")
TEST_DATES = ("2025-03-27", "2025-06-27", "2025-09-27", "2025-12-27")   # round 3: days of the fresh test set
E1_WINDOWS = {"midday": 40, "evening": 72}           # first quarter hour of each 16-step window
E1_STEPS, E1_SCENARIOS, E1_SEED = 16, 10, 101
E1_BATTERY = tuple(np.linspace(-60, 60, 9))
E1_KEEP = (1.0, 0.8, 0.6, 0.4)
BATCHES = (1, 16, 128, 1024)
GATES = {"voltage_mae_v": 0.5, "voltage_p99_v": 2.0, "loading_mae_pts": 2.0, "loading_p99_pts": 5.0}
MAX_EXAMPLES = 25


# ---- states <-> contract ------------------------------------------------------------------------------------------

def to_operating_states(street: str, s: StateArrays, line_ends, house_phase=None, battery_node=None) -> list[OperatingState]:
    node = schema.battery_node(street) if battery_node is None else battery_node
    ends = tuple(tuple(int(v) for v in e) for e in line_ends)
    phases = None if house_phase is None else tuple(int(p) for p in house_phase)
    return [OperatingState(street, ends, s.load_kw[i], s.pv_kw[i], float(s.upstream_pu[i]), float(s.battery_kw[i]),
                           node if s.battery_kw[i] else None, int(s.tap_pos[i]), schema.MODES[int(s.mode[i])],
                           phases, s.pv_kwp[i]) for i in range(len(s))]


# ---- held-out scoring ---------------------------------------------------------------------------------------------

def _score(model, failure, guard, x, labels, rules=RULES, supported=None) -> dict:
    from engine.rules import get_rule
    pred = model.extremes(x)
    el = model.elements(x) if hasattr(model, "elements") else None
    p_fail = failure.proba(x) if failure is not None else None
    out = {"regression": metrics.regression(pred, labels, el, labels.u_pu.shape[1] * 3), "rules": {}}
    for rid in rules:
        r = get_rule(rid)
        d = calibrate.decide(pred, guard, r.vmin_pu, r.vmax_pu, p_fail)
        unsafe = metrics.truly_unsafe(labels, r.vmin_pu, r.vmax_pu)
        out["rules"][rid] = {"guarded": metrics.screening(d["risky"], unsafe), "point": metrics.screening(d["point_unsafe"], unsafe)}
        if supported is not None:                      # as deployed: an unsupported state is risky and goes to the solver
            out["rules"][rid]["deployed"] = metrics.screening(d["risky"] | ~supported, unsafe)
    if supported is not None:
        out["supported_states"] = int(supported.sum())
    return out


def _subsets(test: dataset.Split) -> dict:
    s = test.states
    held = np.array([(int(t), schema.MODES[int(m)]) in generate.HELD_OUT for t, m in zip(s.tap_pos, s.mode)])
    adoption75 = (s.pv_kwp > 0).sum(axis=1) == round(0.75 * s.pv_kwp.shape[1])
    return {"all": np.ones(len(test), bool), "base": ~test.boundary, "boundary": test.boundary,
            "held_out_tap_mode": held, "adoption_75": adoption75}


def gates(reg: dict) -> dict:
    v = reg.get("node_voltage_v") or reg["v_max_v"]
    ld = reg.get("line_loading_pts") or reg["max_line_loading_pts"]
    checks = {"voltage_mae_v": (v["mae"], GATES["voltage_mae_v"]), "voltage_p99_v": (v["p99"], GATES["voltage_p99_v"]),
              "loading_mae_pts": (ld["mae"], GATES["loading_mae_pts"]), "loading_p99_pts": (ld["p99"], GATES["loading_p99_pts"])}
    return {k: {"value": val, "target": tgt, "passed": val is not None and val <= tgt} for k, (val, tgt) in checks.items()}


def score_heldout(street: str, models_root: Path, data_root: Path, selected: str, shipped_round: int, *,
                  split: str = "test", layouts: bool = True) -> tuple[dict, list]:
    """Every candidate, with the round 1 margins and (if run) the round 2 margins, scored once on `split`. With
    layouts=False the support is the per-feature box alone (rounds 1-2 as pre-registered); with True, the shipped one."""
    from backend.v2 import compute
    test = dataset.load_split(street, split, data_root)
    data = train.prepare(test)
    subsets = _subsets(test)
    cand_dir = models_root / "candidates" / street
    sm = load_screener(models_root).models[street]          # the shipped support box (the same train split for all)
    ends = schema.line_ends(compute.network(street))
    supported = np.array([not sm.check(s, layouts=layouts)[0] for s in to_operating_states(street, test.states, ends)])
    out, examples = {"split": split, "support": "shipped (with solar layouts)" if layouts else "per-feature box (rounds 1-2)",
                     "states": {k: int(v.sum()) for k, v in subsets.items()},
                     "supported": {k: int((v & supported).sum()) for k, v in subsets.items()},
                     "rounds": {}, "shipped_round": shipped_round}, []
    for rnd, suffix in ((1, "_guard.json"), (2, "_guard_round2.json")):
        for kind in ("ridge", "lgbm", "mlp"):
            gpath = cand_dir / f"{kind}{suffix}"
            if not gpath.exists():
                continue
            model, failure = predict.load(cand_dir / f"{kind}.npz")
            guard = json.loads(gpath.read_text(encoding="utf-8"))
            subs = {**subsets, "base_supported": subsets["base"] & supported, "boundary_supported": subsets["boundary"] & supported}
            res = {name: _score(model, failure, guard, data.x[m], _take(test.labels, m), supported=supported[m])
                   for name, m in subs.items() if m.any()}
            res["gates_on_base"] = gates(res["base"]["regression"])
            res["gates_on_supported"] = gates(res["base_supported"]["regression"])     # the states the screen accepts
            res["margins_at_limits"] = calibrate.limit_margins(guard)
            out["rounds"].setdefault(str(rnd), {})[kind] = res
            if kind == selected and rnd == shipped_round:
                examples = _heldout_examples(street, model, failure, guard, data, test, supported)
    out["candidates"] = out["rounds"][str(shipped_round)]
    return out, examples


def _take(lab, m):
    from ml.surrogate.teacher import Labels
    return Labels(lab.u_pu[m], lab.line_loading_pct[m], lab.trafo_loading_pct[m], lab.converged[m], lab.passes[m])


def _heldout_examples(street, model, failure, guard, data, test, supported) -> list:
    """Natural disagreements on held-out states: the point prediction (and, if any, the guarded screen) called a state
    safe that the solver found unsafe. The solver's answer is what the system acts on."""
    from engine.rules import get_rule
    pred = model.extremes(data.x)
    p_fail = failure.proba(data.x) if failure is not None else None
    ext = test.labels.extremes()
    rows = []
    for rid in RULES:
        r = get_rule(rid)
        d = calibrate.decide(pred, guard, r.vmin_pu, r.vmax_pu, p_fail)
        unsafe = metrics.truly_unsafe(test.labels, r.vmin_pu, r.vmax_pu)
        for kind, mask in (("guarded screen said safe", supported & unsafe & ~d["risky"]),
                           ("point prediction said safe", supported & unsafe & ~d["point_unsafe"])):
            idx = np.flatnonzero(mask)
            order = idx[np.argsort(-test.boundary[idx].astype(int), kind="stable")][:MAX_EXAMPLES]
            for i in order:
                rows.append({"street": street, "rule": rid, "source": "held-out test split", "type": kind,
                             "family": str(test.family[i]), "boundary_state": bool(test.boundary[i]),
                             "caught_by_guard": bool(d["risky"][i]),
                             "predicted": _ext(pred[i]), "guarded": _ext(d["guarded"][i]),
                             "solver": _ext(ext[i]) | {"converged": bool(test.labels.converged[i])},
                             "solver_response": "unsafe: rejected; only the solver's verdict is used"})
    return rows


def _ext(e) -> dict:
    return {"v_max_v": _r(e[0] * 230, 2), "v_min_v": _r(e[1] * 230, 2), "max_line_loading_pct": _r(e[2], 1),
            "max_trafo_loading_pct": _r(e[3], 1)}


def _r(v, n):
    return None if not np.isfinite(v) else round(float(v), n)


# ---- out of range (2.5) -------------------------------------------------------------------------------------------

def score_ood(street: str, screener, data_root: Path, selected_model) -> dict:
    from engine.rules import get_rule
    ood = dataset.load_ood(street, data_root)
    out = {}
    for kind, item in ood.items():
        states = to_operating_states(street, item["states"], item["line_ends"], item["house_phase"], item["battery_node"])
        screens = screener.screen(states)
        reasons = {}
        for s in screens:
            if s.status == "unsupported":
                key = s.reason.split(" = ")[0] if " = " in s.reason else s.reason
                reasons[key] = reasons.get(key, 0) + 1
        st = item["states"]
        x = schema.features(st.load_kw, st.pv_kw, st.pv_kwp, st.upstream_pu, st.tap_pos, st.battery_kw, st.mode)
        with np.errstate(all="ignore"):
            pred = selected_model.extremes(x)
        r = get_rule("pm10")
        unsafe = metrics.truly_unsafe(item["labels"], r.vmin_pu, r.vmax_pu)
        out[kind] = {"states": len(states), "unsupported": sum(s.status == "unsupported" for s in screens),
                     "risky": sum(s.risky for s in screens), "reasons": reasons,
                     "raw_model_if_not_refused": {"regression": metrics.regression(pred, item["labels"]),
                                                  "point_screen_pm10": metrics.screening(calibrate.crosses(pred, r.vmin_pu, r.vmax_pu), unsafe)}}
    return out


# ---- latency (2.8) ------------------------------------------------------------------------------------------------

def _median_time(fn, reps) -> float:
    fn()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return float(np.median(ts))


def latency(street: str, screener, data_root: Path, reps: int) -> dict:
    from backend.v2 import compute
    net = compute.network(street)
    test = dataset.load_split(street, "test_fresh", data_root)
    out = {}
    for mode in ("fixed_pf", "volt_var"):
        rows = np.flatnonzero(~test.boundary & (test.states.mode == schema.MODES.index(mode)) & (test.states.battery_kw == 0)
                              & (test.states.pv_kwp > 0).all(axis=1))
        sm = screener.models[street]
        ends = schema.line_ends(net)
        rows = np.array([i for i in rows[:4 * max(BATCHES)]
                         if not sm.check(to_operating_states(street, test.states.take([i]), ends)[0])[0]])
        res = {}
        for b in BATCHES:
            pick = test.states.take(rows[:b])
            states = to_operating_states(street, pick, schema.line_ends(net))
            x = np.stack([sm.check(s)[1] for s in states])
            n_rep = reps if b <= 128 else max(2, reps // 4)
            t_screen = _median_time(lambda: screener.screen(states), n_rep)
            t_model = _median_time(lambda: sm.model.extremes(x), n_rep)
            t_build = _median_time(lambda: to_operating_states(street, pick, schema.line_ends(net)), n_rep)
            t_solver = _median_time(lambda: solve_states(net, pick, battery_node=schema.battery_node(street)),
                                    max(2, n_rep // (4 if mode == "volt_var" else 1)))
            res[str(b)] = {"states": int(len(pick)), "screen_s": t_screen, "model_only_s": t_model,
                           "build_states_s": t_build, "solver_s": t_solver,
                           "screen_ms_per_state": round(1000 * t_screen / len(pick), 4),
                           "solver_ms_per_state": round(1000 * t_solver / len(pick), 4),
                           "solver_over_screen": round(t_solver / t_screen, 1)}
        out[mode] = res
    return out


# ---- end-to-end 1: controller-style action screening --------------------------------------------------------------

def _e1_actions():
    acts = [(float(b), float(k)) for k in E1_KEEP for b in E1_BATTERY]
    return sorted(acts, key=lambda a: ((1 - a[1]) * 1000 + abs(a[0]), a[0]))   # least curtailment, then least battery


def e1_job(street: str, date: str, window: str, rule_id: str, models_root: str) -> dict:
    warnings.filterwarnings("ignore")
    from backend.v2 import compute
    from engine.rules import get_rule
    net, r = compute.network(street), get_rule(rule_id)
    screener = load_screener(Path(models_root))
    t0 = time.perf_counter()
    screener.models[street].street_ok()            # one-time check that the street is the trained one (builds it)
    t_once = time.perf_counter() - t0
    node = schema.battery_node(street)
    scn = compute.scenarios(date, net, n=E1_SCENARIOS, seed=E1_SEED)
    steps = slice(E1_WINDOWS[window], E1_WINDOWS[window] + E1_STEPS)
    load = scn.load_kw[:, steps].reshape(-1, net.n_homes)
    avail = scn.pv_per_kwp[:, steps].reshape(-1, 1) * net.house_kwp[None, :]
    up = scn.upstream_pu[:, steps].reshape(-1)
    m = len(up)
    acts = _e1_actions()

    def arrays(a):
        b, k = a
        return StateArrays(load, avail * k, np.tile(net.house_kwp, (m, 1)), up, np.full(m, b), np.zeros(m, int), np.zeros(m, int))

    def unsafe_of(states):
        lab = solve_states(net, states, battery_node=node)
        return metrics.truly_unsafe(lab, r.vmin_pu, r.vmax_pu), lab

    # (a) solve every action in one batch
    t0 = time.perf_counter()
    all_states = StateArrays.concat([arrays(a) for a in acts])
    u_all, lab_all = unsafe_of(all_states)
    truth = u_all.reshape(len(acts), m).any(axis=1)                       # True: the action is unsafe somewhere
    choice_a = next((i for i in range(len(acts)) if not truth[i]), None)
    t_a = time.perf_counter() - t0
    # (b) solver in cost order, stop at the first verified-safe action
    t0, solved_b, choice_b = time.perf_counter(), 0, None
    for i, a in enumerate(acts):
        u, _ = unsafe_of(arrays(a))
        solved_b += m
        if not u.any():
            choice_b = i
            break
    t_b = time.perf_counter() - t0
    # (c) screen everything, verify predicted-safe actions in cost order, then the rest
    t0 = time.perf_counter()
    ops = to_operating_states(street, all_states, schema.line_ends(net))
    d = screener.screen_detail(ops, r)
    t_screen = time.perf_counter() - t0
    risky = d["risky"].reshape(len(acts), m).any(axis=1)
    supported = d["supported"].reshape(len(acts), m).all(axis=1)
    order = [i for i in range(len(acts)) if not risky[i]] + [i for i in range(len(acts)) if risky[i]]
    solved_c, choice_c, overrules = 0, None, []
    for i in order:
        u, lab = unsafe_of(arrays(acts[i]))
        solved_c += m
        if not u.any():
            choice_c = i
            break
        if not risky[i]:
            j = int(np.flatnonzero(u)[0])
            g = d["guarded"].reshape(len(acts), m, 4)[i, j]
            overrules.append({"street": street, "date": date, "window": window, "rule": rule_id, "source": "controller-style run",
                              "action": {"battery_kw": acts[i][0], "keep": acts[i][1]}, "type": "screen said safe",
                              "guarded": _ext(g), "solver": _ext(lab.extremes()[j]) | {"converged": bool(lab.converged[j])},
                              "solver_response": "unsafe: action rejected, the next action was verified"})
    t_c = time.perf_counter() - t0
    false_rej = int((risky & ~truth).sum())
    cost = lambda i: None if i is None else round((1 - acts[i][1]) * 1000 + abs(acts[i][0]), 2)  # noqa: E731
    return {"street": street, "date": date, "window": window, "rule": rule_id, "actions": len(acts), "states_per_action": m,
            "truly_safe_actions": int((~truth).sum()), "screened_safe_actions": int((~risky).sum()),
            "fully_supported_actions": int(supported.sum()), "false_rejections": false_rej,
            "screened_safe_but_unsafe": int((~risky & truth).sum()),
            "choice": {"solve_all": choice_a, "solver_in_cost_order": choice_b, "screen_then_verify": choice_c},
            "choice_action": {"solve_all": None if choice_a is None else acts[choice_a],
                              "screen_then_verify": None if choice_c is None else acts[choice_c]},
            "same_choice_as_solve_all": choice_a == choice_c, "cost_gap": None if choice_a is None or choice_c is None else
            round(cost(choice_c) - cost(choice_a), 2),
            "seconds": {"solve_all": round(t_a, 3), "solver_in_cost_order": round(t_b, 3), "screen_then_verify": round(t_c, 3),
                        "of_which_screening": round(t_screen, 3), "one_time_street_check_not_counted": round(t_once, 3)},
            "solver_states": {"solve_all": len(acts) * m, "solver_in_cost_order": solved_b, "screen_then_verify": solved_c},
            "overrules": overrules}


# ---- end-to-end 2: the whole-day fix tournament -------------------------------------------------------------------

def e2_job(street: str, date: str, rule_id: str, models_root: str) -> dict:
    warnings.filterwarnings("ignore")
    from backend.v2 import compute
    from engine.rules import get_rule
    from ml.surrogate import fixes
    net, r = compute.network(street), get_rule(rule_id)
    rs = compute.robust_set(compute.scenarios(date, net))
    screener = load_screener(Path(models_root))
    screener.models[street].street_ok()            # one-time street check, outside the timed runs
    plain = fixes.assisted_tournament(net, rs, r, None, street=street)
    assisted = fixes.assisted_tournament(net, rs, r, screener, street=street)
    truth = {c["id"]: c["verified"] for c in plain["candidates"]}
    skipped = [c["id"] for c in assisted["candidates"] if c["skipped"]]
    for d in assisted["disagreements"]:
        d.update(street=street, date=date, rule=rule_id, source="fix tournament")
    return {"street": street, "date": date, "rule": rule_id, "candidates": len(plain["candidates"]),
            "skipped": skipped, "false_rejections": [c for c in skipped if truth.get(c)],
            "same_best": plain["best"] == assisted["best"], "fallback_solved": assisted["fallback_solved"],
            "safe_action_found": {"solver_only": plain["safe_action_found"], "assisted": assisted["safe_action_found"]}, "best": {"solver_only": plain["best"], "assisted": assisted["best"]},
            "safe_ranked": {"solver_only": plain["safe_ranked"], "assisted": assisted["safe_ranked"]},
            "timing": {"solver_only": plain["timing"], "assisted": assisted["timing"]},
            "screen_status": {c["id"]: c["screen"]["status"] + (f": {c['screen']['reason']}" if c["screen"]["reason"] else "")
                              for c in assisted["candidates"]},
            "disagreements": assisted["disagreements"]}


# ---- driver -------------------------------------------------------------------------------------------------------

def _summary_e1(rows: list) -> dict:
    t = {k: sum(r["seconds"][k] for r in rows) for k in ("solve_all", "solver_in_cost_order", "screen_then_verify")}
    s = {k: sum(r["solver_states"][k] for r in rows) for k in ("solve_all", "solver_in_cost_order", "screen_then_verify")}
    return {"runs": len(rows), "total_seconds": {k: round(v, 2) for k, v in t.items()}, "solver_states": s,
            "speedup_vs_solve_all": round(t["solve_all"] / t["screen_then_verify"], 2),
            "speedup_vs_cost_order": round(t["solver_in_cost_order"] / t["screen_then_verify"], 2),
            "same_choice_as_solve_all": sum(r["same_choice_as_solve_all"] for r in rows),
            "false_rejections": sum(r["false_rejections"] for r in rows),
            "screened_safe_but_unsafe": sum(r["screened_safe_but_unsafe"] for r in rows),
            "overrules": sum(len(r["overrules"]) for r in rows)}


def _summary_e2(rows: list) -> dict:
    plain = sum(r["timing"]["solver_only"]["total_s"] for r in rows)
    assisted = sum(r["timing"]["assisted"]["total_s"] for r in rows)
    return {"runs": len(rows), "total_seconds": {"solver_only": round(plain, 1), "assisted": round(assisted, 1)},
            "speedup": round(plain / assisted, 3), "skipped_candidates": sum(len(r["skipped"]) for r in rows),
            "candidates": sum(r["candidates"] for r in rows), "false_rejections": sum(len(r["false_rejections"]) for r in rows),
            "same_best": sum(r["same_best"] for r in rows), "disagreements": sum(len(r["disagreements"]) for r in rows),
            "fallback_solved": sum(r["fallback_solved"] for r in rows),
            "runs_with_a_safe_fix": sum(r["safe_action_found"]["solver_only"] for r in rows)}


def write_sample(street: str, data_root: Path, n: int = 200) -> None:
    test = dataset.load_split(street, "test_fresh", data_root)
    idx = np.random.default_rng(0).choice(len(test), size=n, replace=False)
    part = test.take(np.sort(idx))
    np.savez_compressed(dataset.street_dir(street, data_root) / "sample.npz", family=part.family, boundary=part.boundary,
                        **dataset._pack("", part.states, part.labels))


def main(argv=None) -> None:
    warnings.filterwarnings("ignore")
    p = argparse.ArgumentParser()
    p.add_argument("--street", action="append", choices=tuple(schema.BATTERY_NODES))
    p.add_argument("--root", default=str(dataset.DATA_DIR))
    p.add_argument("--models", default=str(artifact.MODEL_DIR))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--skip", action="append", default=[], choices=("heldout", "ood", "latency", "e1", "e2"))
    args = p.parse_args(argv)
    data_root, models_root = Path(args.root), Path(args.models)
    streets = args.street or tuple(schema.BATTERY_NODES)
    dates = TEST_DATES[:1] if args.quick else TEST_DATES
    reps = 3 if args.quick else 15
    screener = load_screener(models_root)
    if screener is None:
        raise SystemExit("no usable surrogate artifact: run scripts.surrogate_train first")
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    report.update({"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "quick": args.quick,
                   "provenance": "simulated states labelled by the power-grid-model solver; not measured data",
                   "environment": {"python": platform.python_version(), "cpu": platform.processor(), "cpu_count": os.cpu_count(),
                                   "device": "cpu (NumPy and LightGBM inference); the GPU was not used",
                                   "note": "timings were taken on a shared developer laptop while other work ran"},
                   "protocol": {"rules": RULES, "test_dates": dates, "e1": {"windows": E1_WINDOWS, "steps": E1_STEPS,
                                "scenarios": E1_SCENARIOS, "seed": E1_SEED, "battery_kw": E1_BATTERY, "keep": E1_KEEP, "tap": 0},
                                "latency_batches": BATCHES, "latency_repetitions": reps, "gates": GATES},
                   "streets": report.get("streets", {})})
    examples = json.loads(DISAGREEMENTS.read_text(encoding="utf-8"))["examples"] if DISAGREEMENTS.exists() else []
    for street in streets:
        rec = report["streets"].setdefault(street, {})
        manifest = json.loads((models_root / street / artifact.MANIFEST_FILE).read_text(encoding="utf-8"))
        selected = manifest["model_kind"]
        rec["selected"] = selected
        rec["support"] = {"taps": manifest["taps"], "modes": manifest["modes"], "battery_node": manifest["battery_node"],
                          "battery_kw": [manifest["box"]["min"][manifest["feature_names"].index("battery_kw")],
                                         manifest["box"]["max"][manifest["feature_names"].index("battery_kw")]],
                          "upstream_pu": [manifest["box"]["min"][manifest["feature_names"].index("upstream_pu")],
                                          manifest["box"]["max"][manifest["feature_names"].index("upstream_pu")]],
                          "not_screened": manifest["not_screened"]}
        rec["guard"] = {"at_limits": calibrate.limit_margins(manifest["guard"]), "round": manifest.get("guard_round", 1)}
        if "heldout" not in args.skip:
            print(f"{street}: held-out scoring", flush=True)
            rec["heldout"], _ = score_heldout(street, models_root, data_root, selected, manifest.get("guard_round", 1),
                                              split="test", layouts=False)
            rec["heldout_fresh"], ex = score_heldout(street, models_root, data_root, selected, manifest.get("guard_round", 1),
                                                     split="test_fresh", layouts=True)
            examples = [e for e in examples if not (e["street"] == street and e["source"] == "held-out test split")] + ex
            write_sample(street, data_root)
        if "ood" not in args.skip:
            print(f"{street}: out-of-range routing", flush=True)
            rec["out_of_range"] = score_ood(street, screener, data_root, screener.models[street].model)
        if "latency" not in args.skip:
            print(f"{street}: latency", flush=True)
            rec["latency"] = latency(street, screener, data_root, reps)
        _save(report, examples)
    jobs1 = [(s, d, w, r) for s in streets for d in dates for w in E1_WINDOWS for r in RULES]
    jobs2 = [(s, d, r) for s in streets for d in dates for r in RULES]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        if "e1" not in args.skip:
            print(f"controller-style runs: {len(jobs1)}", flush=True)
            rows = list(pool.map(e1_job, *zip(*jobs1), [str(models_root)] * len(jobs1)))
            for street in streets:
                mine = [r for r in rows if r["street"] == street]
                report["streets"][street]["e1_controller_style"] = {"summary": _summary_e1(mine),
                                                                    "runs": [{k: v for k, v in r.items() if k != "overrules"} for r in mine]}
            examples = [e for e in examples if e["source"] != "controller-style run"] + [o for r in rows for o in r["overrules"]][:200]
            _save(report, examples)
        if "e2" not in args.skip:
            print(f"fix tournaments: {len(jobs2)} (each solved twice)", flush=True)
            rows = list(pool.map(e2_job, *zip(*jobs2), [str(models_root)] * len(jobs2)))
            for street in streets:
                mine = [r for r in rows if r["street"] == street]
                report["streets"][street]["e2_fix_tournament"] = {"summary": _summary_e2(mine),
                                                                  "runs": [{k: v for k, v in r.items() if k != "disagreements"} for r in mine]}
            examples = [e for e in examples if e["source"] != "fix tournament"] + [d for r in rows for d in r["disagreements"]]
            _save(report, examples)
    print("done", flush=True)


def _save(report: dict, examples: list) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, default=_json), encoding="utf-8")
    by = {}
    for e in examples:
        by[(e["source"], e["type"])] = by.get((e["source"], e["type"]), 0) + 1
    DISAGREEMENTS.write_text(json.dumps({"note": "Examples of states or actions the surrogate judged differently from the "
                                         f"solver, and what the system did (at most {MAX_EXAMPLES} per street, rule and type; "
                                         "the full counts are in surrogate_evaluation.json). The solver's verdict always stands.",
                                         "counts": [{"source": k[0], "type": k[1], "rows": v} for k, v in sorted(by.items())],
                                         "examples": examples}, indent=1, default=_json), encoding="utf-8")


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    main()
