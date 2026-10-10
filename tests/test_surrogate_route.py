"""GET /surrogate: the surrogate's evidence for the dashboard, read from the evaluation files; never computed on request."""
import json

from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings


def _client(tmp_path) -> TestClient:
    (tmp_path / "models").mkdir(exist_ok=True)
    return TestClient(create_app(Settings(code_version="abc1234", model_dir=tmp_path / "models")), raise_server_exceptions=False)


def _screen(fs=0, unsafe=10, fr=2, safe=20):
    return {"unsafe_as_safe": fs, "truly_unsafe": unsafe, "false_rejections": fr, "truly_safe": safe, "miss_rate_upper95": 0.26,
            "false_rejection_rate": fr / safe, "recall": 1 - fs / unsafe, "precision": 0.8}


def _cand(fr=2):
    reg = {"node_voltage_v": {"mae": 0.2, "p99": 1.1}, "line_loading_pts": {"mae": 0.5, "p99": 2.0},
           "v_max_v": {"mae": 0.3, "p99": 1.2}, "max_line_loading_pts": {"mae": 0.4, "p99": 1.5}, "vuf_pts": {"mae": 0.03, "p99": 0.1}}
    rules = {r: {"guarded": _screen(fr=fr), "point": _screen(fs=3), "deployed": _screen(fr=fr)} for r in ("up_2005", "pm10")}
    part = {"regression": reg, "rules": rules}
    return {"all": part, "base": part, "boundary": part, "held_out_tap_mode": part, "switched_layout": part,
            "random_solar_layout": part, "gates_on_base": {"voltage_mae_v": {"value": 0.2, "target": 0.5, "passed": True},
                                                           "voltage_p99_v": {"value": 2.5, "target": 2.0, "passed": False}}}


def _write_reports(tmp_path, *, e2=True, archive=True):
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    street = {
        "selected": "mlp",
        "support": {"taps": [0, 1, 2], "modes": ["fixed_pf"], "battery_nodes": [21, 65], "battery_kw": [-100, 100],
                    "upstream_pu": [0.85, 1.2], "line_layouts": 4, "novelty": {"threshold": 9.0, "components": 40}},
        "guard": {"at_limits": {"up_2005": {"v_max_v": 1.4, "v_min_v": 1.1}, "pm10": {"v_max_v": 2.1, "v_min_v": 1.3},
                                "line_pts": 1.5, "trafo_pts": 1.2}, "round": 4},
        "heldout": {"states": {"all": 50, "base": 40, "boundary": 10}, "supported": {"all": 45},
                    "candidates": {"ridge": _cand(), "lgbm": _cand(), "mlp": _cand(fr=1)}},
        "out_of_range": {"tap_negative": {"states": 250, "unsupported": 250, "risky": 250, "reasons": {"tap -1": 125}}},
        "latency": {"fixed_pf": {"1": {"screen_ms_per_state": 0.5, "solver_ms_per_state": 2.4, "states": 1}}},
        "e1_controller_style": {"summary": {"runs": 4, "speedup_vs_solve_all": 3.0, "speedup_vs_cost_order": 1.2,
                                            "same_choice_as_solve_all": 4, "false_rejections": 1, "overrules": 0,
                                            "runs_with_a_safe_action": 2}},
    }
    if e2:
        street["e2_fix_tournament"] = {"summary": {"runs": 2, "speedup": 1.05, "skipped_candidates": 3, "candidates": 50,
                                                   "false_rejections": 0, "same_best": 2, "disagreements": 0}}
    (reports / "surrogate_evaluation.json").write_text(json.dumps(
        {"created_utc": "2026-10-10T12:00:00+00:00", "provenance": "simulated", "streets": {"benchmark_250": street}}))
    (reports / "surrogate_bakeoff.json").write_text(json.dumps(
        {"streets": {"benchmark_250": {"selected": "mlp", "reason": "lowest", "selected_at_utc": "2026-10-10T11:00:00+00:00",
                                       "states": {s: {"total": 10, "boundary": 2, "solver_failures": 0}
                                                  for s in ("train", "tune", "calibrate")}}}}))
    if archive:
        (reports / "surrogate_rounds1-3").mkdir(exist_ok=True)
        old = {"selected": "mlp", "heldout": {"rounds": {"1": {"mlp": _cand(fr=9)}, "2": {"mlp": _cand(fr=8)}}},
               "heldout_fresh": {"candidates": {"mlp": _cand(fr=7)}}}
        (reports / "surrogate_rounds1-3" / "surrogate_evaluation.json").write_text(json.dumps({"streets": {"benchmark_250": old}}))
    examples = [{"source": "held-out test split", "type": "point prediction said safe", "street": "benchmark_250", "rule": "pm10",
                 "caught_by_guard": True, "predicted": {"v_max_v": 252.0}, "guarded": {"v_max_v": 253.5},
                 "solver": {"v_max_v": 253.2, "converged": True}, "solver_response": "unsafe: rejected"}] * 30
    (reports / "surrogate_disagreements.json").write_text(json.dumps(
        {"note": "n", "counts": [{"source": "held-out test split", "type": "point prediction said safe", "rows": 30}],
         "examples": examples}))


def test_missing_evaluation_is_503_with_the_command(tmp_path):
    r = _client(tmp_path).get("/surrogate")
    assert r.status_code == 503 and "scripts.surrogate_evaluate" in r.json()["error"]["message"]


def test_summary_has_every_section_and_says_the_screener_is_off_without_an_artifact(tmp_path):
    _write_reports(tmp_path)
    body = _client(tmp_path).get("/surrogate").json()
    assert body["screener"]["active"] is False and body["screener"]["reason"]
    st = body["streets"][0]
    assert st["id"] == "benchmark_250" and st["selected"] == "mlp" and st["selection_reason"] == "lowest"
    assert [c["kind"] for c in st["candidates"]] == ["ridge", "lgbm", "mlp"] and sum(c["selected"] for c in st["candidates"]) == 1
    assert st["candidates"][2]["vuf_mae_pts"] == 0.03
    assert {g["name"] for g in st["gates"]} == {"voltage_mae_v", "voltage_p99_v"} and not all(g["passed"] for g in st["gates"])
    assert {(s["rule"], s["split"]) for s in st["screening"]} >= {("up_2005", "boundary"), ("pm10", "switched_layout"),
                                                                  ("pm10", "random_solar_layout")}
    assert st["screening"][0]["guarded"]["miss_rate_upper95"] == 0.26
    assert st["out_of_range"] == [{"kind": "tap_negative", "states": 250, "unsupported": 250}]
    assert st["latency"][0]["solver_ms_per_state"] == 2.4
    assert st["e1"]["speedup_vs_solve_all"] == 3.0 and st["e2"]["skipped_candidates"] == 3
    assert st["states"]["train"] == 10 and st["states"]["boundary_test"] == 10 and st["states"]["test_supported"] == 45
    assert st["support"]["battery_nodes"] == [21, 65] and st["shipped_round"] == 4
    assert st["guard_v"] == [1.4, 1.1] and st["guard_loading_pts"] == [1.5, 1.2]
    assert len(body["disagreements"]["examples"]) <= 12 and body["disagreements"]["counts"][0]["rows"] == 30
    assert "simulated" in body["provenance"]


def test_rounds_one_to_three_come_from_the_archive_and_four_from_the_current_run(tmp_path):
    _write_reports(tmp_path)
    st = _client(tmp_path).get("/surrogate").json()["streets"][0]
    rows = {(r["round"], r["rule"]): r for r in st["rounds"]}
    assert set(rows) == {(n, r) for n in (1, 2, 3, 4) for r in ("up_2005", "pm10")}
    assert [rows[(n, "pm10")]["false_rejections"] for n in (1, 2, 3, 4)] == [9, 8, 7, 1]


def test_a_street_without_earlier_rounds_shows_round_four_only(tmp_path):
    _write_reports(tmp_path, archive=False)
    st = _client(tmp_path).get("/surrogate").json()["streets"][0]
    assert {r["round"] for r in st["rounds"]} == {4}


def test_accuracy_and_targets_use_the_states_the_screen_accepts(tmp_path):
    _write_reports(tmp_path)
    path = tmp_path / "reports" / "surrogate_evaluation.json"
    ev = json.loads(path.read_text())
    mlp = ev["streets"]["benchmark_250"]["heldout"]["candidates"]["mlp"]
    mlp["base_supported"] = {"regression": {"node_voltage_v": {"mae": 0.15, "p99": 0.9}, "line_loading_pts": {"mae": 0.2, "p99": 1.0}}}
    mlp["gates_on_supported"] = {"voltage_mae_v": {"value": 0.15, "target": 0.5, "passed": True}}
    path.write_text(json.dumps(ev))
    st = _client(tmp_path).get("/surrogate").json()["streets"][0]
    row = next(c for c in st["candidates"] if c["kind"] == "mlp")
    assert row["voltage_mae_v"] == 0.15 and st["gates"] == [{"name": "voltage_mae_v", "value": 0.15, "target": 0.5, "passed": True}]


def test_a_section_not_run_is_null_not_invented(tmp_path):
    _write_reports(tmp_path, e2=False)
    st = _client(tmp_path).get("/surrogate").json()["streets"][0]
    assert st["e2"] is None


def test_all_disagreements_are_available(tmp_path):
    _write_reports(tmp_path)
    body = _client(tmp_path).get("/surrogate/disagreements").json()
    assert len(body["examples"]) == 30
