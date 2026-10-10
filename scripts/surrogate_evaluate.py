"""Score the surrogate once on the held-out splits and measure it inside complete candidate evaluation (2.3, 2.5-2.8).
Round 4 (docs/DECISIONS.md, Addition 2).

    python -m scripts.surrogate_evaluate              # every street with an artifact; run after scripts.surrogate_train
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
VUF_LIMIT = 2.0                      # an informative extra check (a common planning limit), not a pre-registered target
TEST_DATES = ("2025-03-07", "2025-06-07", "2025-09-07", "2025-12-07")   # round 4 test days
E1_WINDOWS = {"midday": 40, "evening": 72}           # first quarter hour of each 16-step window
E1_STEPS, E1_SCENARIOS, E1_SEED = 16, 10, 101
E1_BATTERY = tuple(np.linspace(-60, 60, 9))
E1_KEEP = (1.0, 0.8, 0.6, 0.4)
E1_ALWAYS_SOLVED = 3                 # round 4, item 6: the cheapest actions are solved whatever the screen says
BATCHES = (1, 16, 128, 1024)
GATES = {"voltage_mae_v": 0.5, "voltage_p99_v": 2.0, "loading_mae_pts": 2.0, "loading_p99_pts": 5.0}
MAX_EXAMPLES = 25


# ---- states <-> contract ------------------------------------------------------------------------------------------

def to_operating_states(street: str, s: StateArrays, layouts: list, house_phase=None) -> list[OperatingState]:
    """`layouts[k]` is the line layout of topology index k (a list of line ends, or a Network)."""
    ends = [tuple(tuple(int(v) for v in e) for e in (schema.line_ends(t) if hasattr(t, "line_from") else t)) for t in layouts]
    phases = None if house_phase is None else tuple(int(p) for p in house_phase)
    return [OperatingState(street, ends[int(s.topology[i])], s.load_kw[i], s.pv_kw[i], float(s.upstream_pu[i]),
                           float(s.battery_kw[i]), int(s.battery_node[i]) if s.battery_kw[i] else None, int(s.tap_pos[i]),
                           schema.MODES[int(s.mode[i])], phases, s.pv_kwp[i]) for i in range(len(s))]


# ---- held-out scoring ---------------------------------------------------------------------------------------------

def _score(model, failure, guard, x, labels, supported, rules=RULES) -> dict:
    from engine.rules import get_rule
    pred = model.outputs(x)
    el = model.elements(x) if hasattr(model, "elements") else None
    p_fail = failure.proba(x) if failure is not None else None
    out = {"regression": metrics.regression(pred, labels, el, labels.u_pu.shape[1] * 3), "rules": {},
           "supported_states": int(supported.sum())}
    for rid in rules:
        r = get_rule(rid)
        d = calibrate.decide(pred, guard, r.vmin_pu, r.vmax_pu, p_fail)
        unsafe = metrics.truly_unsafe(labels, r.vmin_pu, r.vmax_pu)
        out["rules"][rid] = {"guarded": metrics.screening(d["risky"], unsafe), "point": metrics.screening(d["point_unsafe"], unsafe),
                             "deployed": metrics.screening(d["risky"] | ~supported, unsafe)}   # unsupported = risky
    r = get_rule("pm10")
    d = calibrate.decide(pred, guard, r.vmin_pu, r.vmax_pu, p_fail, vuf_limit=VUF_LIMIT)
    unsafe = metrics.truly_unsafe(labels, r.vmin_pu, r.vmax_pu, vuf_limit=VUF_LIMIT)
    out["rules"]["pm10_with_vuf_2pct"] = {"deployed": metrics.screening(d["risky"] | ~supported, unsafe)}
    return out


def _subsets(test: dataset.Split) -> dict:
    s = test.states
    held = np.array([(int(t), schema.MODES[int(m)]) in generate.HELD_OUT for t, m in zip(s.tap_pos, s.mode)])
    return {"all": np.ones(len(test), bool), "base": ~test.boundary, "boundary": test.boundary,
            "held_out_tap_mode": held, "switched_layout": s.topology > 0, "battery_on": s.battery_kw != 0}


def gates(reg: dict) -> dict:
    v = reg.get("node_voltage_v") or reg["v_max_v"]
    ld = reg.get("line_loading_pts") or reg["max_line_loading_pts"]
    checks = {"voltage_mae_v": (v["mae"], GATES["voltage_mae_v"]), "voltage_p99_v": (v["p99"], GATES["voltage_p99_v"]),
              "loading_mae_pts": (ld["mae"], GATES["loading_mae_pts"]), "loading_p99_pts": (ld["p99"], GATES["loading_p99_pts"])}
    return {k: {"value": val, "target": tgt, "passed": val is not None and val <= tgt} for k, (val, tgt) in checks.items()}


def _layout_kinds(street: str, test: dataset.Split, data_root: Path) -> np.ndarray:
    manifest = json.loads((dataset.street_dir(street, data_root) / "manifest.json").read_text(encoding="utf-8"))
    kind = {f["id"]: f["layout"] for f in manifest["families"]}
    return np.array([kind[str(f)] for f in test.family])


def score_heldout(street: str, models_root: Path, data_root: Path, selected: str) -> tuple[dict, list]:
    """Every candidate scored once on the round 4 test split, with the shipped support (box, layouts, nodes, novelty)."""
    from backend.v2 import compute
    test = dataset.load_split(street, "test", data_root)
    data = train.prepare(test, street)
    subsets = _subsets(test)
    layout_kind = _layout_kinds(street, test, data_root)
    subsets.update({"random_solar_layout": layout_kind == "random", "planning_75": layout_kind == "planning:0.75"})
    sm = load_screener(models_root).models[street]
    layouts = schema.topologies(compute.network(street))
    supported = np.array([not sm.check(s)[0] for s in to_operating_states(street, test.states, layouts)])
    subsets.update({"base_supported": subsets["base"] & supported, "boundary_supported": subsets["boundary"] & supported})
    cand_dir = models_root / "candidates" / street
    out = {"split": "test (round 4: days 7 and 17 of the test months)", "support": "shipped",
           "states": {k: int(v.sum()) for k, v in subsets.items()},
           "supported": {k: int((v & supported).sum()) for k, v in subsets.items()}, "candidates": {}}
    examples = []
    for kind in ("ridge", "lgbm", "mlp"):
        model, failure, _ = predict.load(cand_dir / f"{kind}.npz")
        guard = json.loads((cand_dir / f"{kind}_guard.json").read_text(encoding="utf-8"))
        res = {name: _score(model, failure, guard, data.x[m], test.labels.take(m), supported[m])
               for name, m in subsets.items() if m.any()}
        res["gates_on_base"] = gates(res["base"]["regression"])
        res["gates_on_supported"] = gates(res["base_supported"]["regression"])
        res["margins_at_limits"] = calibrate.limit_margins(guard)
        out["candidates"][kind] = res
        if kind == selected:
            examples = _heldout_examples(street, model, failure, guard, data, test, supported)
    return out, examples


def _heldout_examples(street, model, failure, guard, data, test, supported) -> list:
    """Natural disagreements on held-out states the screen accepts: the point prediction (and, if any, the guarded
    screen) called a state safe that the solver found unsafe. The solver's answer is what the system acts on."""
    from engine.rules import get_rule
    pred = model.outputs(data.x)
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
                             "caught_by_guard": bool(d["risky"][i]), "predicted": _ext(pred[i]), "guarded": _ext(d["guarded"][i]),
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
    from backend.v2 import compute
    from engine.rules import get_rule
    ood = dataset.load_ood(street, data_root)
    layouts = schema.topologies(compute.network(street))
    out = {}
    for kind, item in ood.items():
        st = item["states"]
        lay = [item["line_ends"]] if kind in ("phase_map", "layout") else layouts
        states = to_operating_states(street, st, lay, item["house_phase"] if kind == "phase_map" else None)
        screens = screener.screen(states)
        reasons = {}
        for s in screens:
            if s.status == "unsupported":
                key = s.reason.split(" = ")[0].split(" (")[0]
                reasons[key] = reasons.get(key, 0) + 1
        x = train.state_features(st, street)
        with np.errstate(all="ignore"):
            pred = selected_model.outputs(x)
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
    layouts = schema.topologies(net)
    test = dataset.load_split(street, "test", data_root)
    sm = screener.models[street]
    out = {}
    for mode in ("fixed_pf", "volt_var"):
        s = test.states
        rows = np.flatnonzero(~test.boundary & (s.mode == schema.MODES.index(mode)) & (s.battery_kw == 0) & (s.topology == 0))
        ok = np.array([not sm.check(st)[0] for st in to_operating_states(street, s.take(rows), layouts)], bool)
        rows = rows[ok] if len(rows) else rows.astype(int)
        res = {"accepted_test_states": int(len(rows))}
        for b in BATCHES:
            if len(rows) < b:                       # not enough states the screen accepts for this batch size
                res[str(b)] = None
                continue
            pick = s.take(rows[:b])
            states = to_operating_states(street, pick, layouts)
            x = np.stack([sm.check(st)[1] for st in states])
            n_rep = reps if b <= 128 else max(2, reps // 4)
            t_screen = _median_time(lambda: screener.screen(states), n_rep)
            t_model = _median_time(lambda: sm.model.outputs(x), n_rep)
            t_solver = _median_time(lambda: solve_states(net, pick), max(2, n_rep // (4 if mode == "volt_var" else 1)))
            res[str(b)] = {"states": int(len(pick)), "screen_s": t_screen, "model_only_s": t_model, "solver_s": t_solver,
                           "screen_ms_per_state": round(1000 * t_screen / len(pick), 4),
                           "solver_ms_per_state": round(1000 * t_solver / len(pick), 4),
                           "solver_over_screen": round(t_solver / t_screen, 1)}
        out[mode] = res
    return out


# ---- end-to-end 1: controller-style action screening --------------------------------------------------------------

def _e1_actions():
    acts = [(float(b), float(k)) for k in E1_KEEP for b in E1_BATTERY]
    return sorted(acts, key=lambda a: ((1 - a[1]) * 1000 + abs(a[0]), a[0]))   # least curtailment, then least battery


def e1_order(risky: np.ndarray, always: int = E1_ALWAYS_SOLVED) -> list[int]:
    """Actions are in cost order: the cheapest `always` first whatever the screen says, then the screened-safe ones,
    then the rest."""
    n = len(risky)
    head = list(range(min(always, n)))
    return head + [i for i in range(len(head), n) if not risky[i]] + [i for i in range(len(head), n) if risky[i]]


def e1_job(street: str, date: str, window: str, rule_id: str, models_root: str) -> dict:
    warnings.filterwarnings("ignore")
    from backend.v2 import compute
    from engine.fixes.catalog import worst_node
    from engine.rules import get_rule
    net, r = compute.network(street), get_rule(rule_id)
    screener = load_screener(Path(models_root))
    t0 = time.perf_counter()
    screener.models[street].street_ok()            # one-time check that the street is the trained one (builds it)
    t_once = time.perf_counter() - t0
    scn = compute.scenarios(date, net, n=E1_SCENARIOS, seed=E1_SEED)
    node = worst_node(net, compute.robust_set(scn))                 # the controller's default battery position
    steps = slice(E1_WINDOWS[window], E1_WINDOWS[window] + E1_STEPS)
    load = scn.load_kw[:, steps].reshape(-1, net.n_homes)
    avail = scn.pv_per_kwp[:, steps].reshape(-1, 1) * net.house_kwp[None, :]
    up = scn.upstream_pu[:, steps].reshape(-1)
    m = len(up)
    acts = _e1_actions()
    layouts = schema.topologies(net)

    def arrays(a):
        b, k = a
        return StateArrays(load, avail * k, np.tile(net.house_kwp, (m, 1)), up, np.full(m, b), np.zeros(m, int),
                           np.zeros(m, int), np.full(m, node if b else -1), np.zeros(m, int))

    def unsafe_of(states):
        lab = solve_states(net, states)
        return metrics.truly_unsafe(lab, r.vmin_pu, r.vmax_pu), lab

    t0 = time.perf_counter()                                        # (a) solve every action in one batch
    all_states = StateArrays.concat([arrays(a) for a in acts])
    u_all, _ = unsafe_of(all_states)
    truth = u_all.reshape(len(acts), m).any(axis=1)                 # True: the action is unsafe somewhere
    choice_a = next((i for i in range(len(acts)) if not truth[i]), None)
    t_a = time.perf_counter() - t0
    t0, solved_b, choice_b = time.perf_counter(), 0, None           # (b) the solver in cost order, first safe wins
    for i, a in enumerate(acts):
        u, _ = unsafe_of(arrays(a))
        solved_b += m
        if not u.any():
            choice_b = i
            break
    t_b = time.perf_counter() - t0
    t0 = time.perf_counter()                                        # (c) screen, then verify in e1_order
    ops = to_operating_states(street, all_states, layouts)
    d = screener.screen_detail(ops, r)
    t_screen = time.perf_counter() - t0
    risky = d["risky"].reshape(len(acts), m).any(axis=1)
    supported = d["supported"].reshape(len(acts), m).all(axis=1)
    solved_c, choice_c, overrules = 0, None, []
    for i in e1_order(risky):
        u, lab = unsafe_of(arrays(acts[i]))
        solved_c += m
        if not u.any():
            choice_c = i
            break
        if not risky[i]:
            j = int(np.flatnonzero(u)[0])
            g = d["guarded"].reshape(len(acts), m, -1)[i, j]
            overrules.append({"street": street, "date": date, "window": window, "rule": rule_id, "source": "controller-style run",
                              "action": {"battery_kw": acts[i][0], "keep": acts[i][1]}, "type": "screen said safe",
                              "guarded": _ext(g), "solver": _ext(lab.extremes()[j]) | {"converged": bool(lab.converged[j])},
                              "solver_response": "unsafe: action rejected, the next action was verified"})
    t_c = time.perf_counter() - t0
    cost = lambda i: None if i is None else round((1 - acts[i][1]) * 1000 + abs(acts[i][0]), 2)  # noqa: E731
    return {"street": street, "date": date, "window": window, "rule": rule_id, "battery_node": int(node),
            "battery_node_trained": int(node) in schema.battery_nodes(street), "actions": len(acts), "states_per_action": m,
            "truly_safe_actions": int((~truth).sum()), "screened_safe_actions": int((~risky).sum()),
            "fully_supported_actions": int(supported.sum()), "false_rejections": int((risky & ~truth).sum()),
            "screened_safe_but_unsafe": int((~risky & truth).sum()),
            "choice": {"solve_all": choice_a, "solver_in_cost_order": choice_b, "screen_then_verify": choice_c},
            "same_choice_as_solve_all": choice_a == choice_c,
            "cost_gap": None if choice_a is None or choice_c is None else round(cost(choice_c) - cost(choice_a), 2),
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
            "safe_action_found": {"solver_only": plain["safe_action_found"], "assisted": assisted["safe_action_found"]},
            "best": {"solver_only": plain["best"], "assisted": assisted["best"]},
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
            "runs_with_a_safe_action": sum(r["truly_safe_actions"] > 0 for r in rows),
            "false_rejections": sum(r["false_rejections"] for r in rows),
            "screened_safe_but_unsafe": sum(r["screened_safe_but_unsafe"] for r in rows),
            "overrules": sum(len(r["overrules"]) for r in rows),
            "battery_node_untrained_runs": sum(not r.get("battery_node_trained", True) for r in rows)}


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
    test = dataset.load_split(street, "test", data_root)
    idx = np.random.default_rng(0).choice(len(test), size=n, replace=False)
    part = test.take(np.sort(idx))
    np.savez_compressed(dataset.street_dir(street, data_root) / "sample.npz", family=part.family, boundary=part.boundary,
                        **dataset._pack("", part.states, part.labels))


def main(argv=None) -> None:
    global REPORT, DISAGREEMENTS
    warnings.filterwarnings("ignore")
    p = argparse.ArgumentParser()
    p.add_argument("--street", action="append", choices=schema.STREETS)
    p.add_argument("--root", default=str(dataset.DATA_DIR))
    p.add_argument("--models", default=str(artifact.MODEL_DIR))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--skip", action="append", default=[], choices=("heldout", "ood", "latency", "e1", "e2"))
    p.add_argument("--report", default=str(REPORT), help="a separate file lets several streets be evaluated in parallel")
    p.add_argument("--disagreements", default=str(DISAGREEMENTS))
    args = p.parse_args(argv)
    REPORT, DISAGREEMENTS = Path(args.report), Path(args.disagreements)
    data_root, models_root = Path(args.root), Path(args.models)
    screener = load_screener(models_root)
    if screener is None:
        raise SystemExit("no usable surrogate artifact: run scripts.surrogate_train first")
    streets = args.street or screener.streets
    dates = TEST_DATES[:1] if args.quick else TEST_DATES
    reps = 3 if args.quick else 15
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    report.update({"round": 4, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "quick": args.quick,
                   "provenance": "simulated states labelled by the power-grid-model solver; not measured data",
                   "environment": {"python": platform.python_version(), "cpu": platform.processor(), "cpu_count": os.cpu_count(),
                                   "device": "cpu (NumPy and LightGBM inference); the GPU was not used",
                                   "note": "timings were taken on a shared developer laptop while other work ran"},
                   "protocol": {"rules": RULES, "vuf_limit_extra": VUF_LIMIT, "test_dates": dates,
                                "e1": {"windows": E1_WINDOWS, "steps": E1_STEPS, "scenarios": E1_SCENARIOS, "seed": E1_SEED,
                                       "battery_kw": E1_BATTERY, "keep": E1_KEEP, "tap": 0, "always_solved": E1_ALWAYS_SOLVED,
                                       "battery_node": "catalog.worst_node of the run's scenarios (the controller default)"},
                                "latency_batches": BATCHES, "latency_repetitions": reps, "gates": GATES},
                   "streets": report.get("streets", {})})
    examples = json.loads(DISAGREEMENTS.read_text(encoding="utf-8"))["examples"] if DISAGREEMENTS.exists() else []
    for street in streets:
        rec = report["streets"].setdefault(street, {})
        manifest = json.loads((models_root / street / artifact.MANIFEST_FILE).read_text(encoding="utf-8"))
        selected = manifest["model_kind"]
        names = manifest["feature_names"]
        bat = [i for i, n in enumerate(names) if n.startswith("battery_kw_at_")]
        rec.update(selected=selected, guard={"at_limits": calibrate.limit_margins(manifest["guard"]), "round": 4},
                   support={"taps": manifest["taps"], "modes": manifest["modes"], "battery_nodes": manifest["battery_nodes"],
                            "battery_kw": [min(manifest["box"]["min"][i] for i in bat), max(manifest["box"]["max"][i] for i in bat)],
                            "upstream_pu": [manifest["box"]["min"][names.index("upstream_pu")],
                                            manifest["box"]["max"][names.index("upstream_pu")]],
                            "line_layouts": len(manifest["line_layouts"]), "novelty": manifest["novelty"],
                            "not_screened": manifest["not_screened"]})
        if "heldout" not in args.skip:
            print(f"{street}: held-out scoring", flush=True)
            rec["heldout"], ex = score_heldout(street, models_root, data_root, selected)
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


def merge(parts: list[Path], report: Path = REPORT, disagreements: Path = DISAGREEMENTS) -> None:
    """Combine reports written by parallel runs (separate --report files): streets are merged, examples concatenated."""
    out, examples = {}, []
    for part in parts:
        r = json.loads(part.read_text(encoding="utf-8"))
        streets = out.get("streets", {})
        for sid, rec in r.get("streets", {}).items():
            streets.setdefault(sid, {}).update(rec)
        out.update({k: v for k, v in r.items() if k != "streets"}, streets=streets)
        d = part.with_name(part.stem.replace("evaluation", "disagreements") + part.suffix)
        if d.exists():
            examples += json.loads(d.read_text(encoding="utf-8"))["examples"]
    global REPORT, DISAGREEMENTS
    REPORT, DISAGREEMENTS = report, disagreements
    _save(out, examples)
