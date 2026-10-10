"""GET /surrogate: the surrogate's evidence for the dashboard, read from the evaluation files; never computed on request."""
import json

from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings


def _client(tmp_path) -> TestClient:
    (tmp_path / "models").mkdir(exist_ok=True)
    return TestClient(create_app(Settings(code_version="abc1234", model_dir=tmp_path / "models")), raise_server_exceptions=False)


def _screen(fs=0, unsafe=10, fr=2, safe=20):
    return {"unsafe_as_safe": fs, "truly_unsafe": unsafe, "false_rejections": fr, "truly_safe": safe,
            "false_rejection_rate": fr / safe, "recall": 1 - fs / unsafe, "precision": 0.8}


def _cand():
    reg = {"node_voltage_v": {"mae": 0.2, "p99": 1.1}, "line_loading_pts": {"mae": 0.5, "p99": 2.0},
           "v_max_v": {"mae": 0.3, "p99": 1.2}, "max_line_loading_pts": {"mae": 0.4, "p99": 1.5}}
    rules = {r: {"guarded": _screen(), "point": _screen(fs=3)} for r in ("up_2005", "pm10")}
    part = {"regression": reg, "rules": rules}
    return {"all": part, "base": part, "boundary": part, "held_out_tap_mode": part,
            "gates_on_base": {"voltage_mae_v": {"value": 0.2, "target": 0.5, "passed": True},
                              "voltage_p99_v": {"value": 2.5, "target": 2.0, "passed": False}}}


def _write_reports(tmp_path, *, e2=True):
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    street = {
        "selected": "mlp", "support": {"taps": [0, 1, 2], "modes": ["fixed_pf"], "battery_node": 65, "battery_kw": [-100, 100],
                                       "upstream_pu": [0.85, 1.2], "not_screened": ["voltage unbalance (VUF)"]},
        "guard": {"at_limits": {"up_2005": {"v_max_v": 1.4, "v_min_v": 1.1}, "pm10": {"v_max_v": 2.1, "v_min_v": 1.3},
                                "line_pts": 1.5, "trafo_pts": 1.2}, "round": 2},
        "heldout": {"states": {"all": 100, "base": 80, "boundary": 20, "held_out_tap_mode": 10}, "shipped_round": 2,
                    "rounds": {"1": {"mlp": _cand()}, "2": {"ridge": _cand(), "lgbm": _cand(), "mlp": _cand()}},
                    "candidates": {"ridge": _cand(), "lgbm": _cand(), "mlp": _cand()}},
        "out_of_range": {"tap_negative": {"states": 250, "unsupported": 250, "risky": 250, "reasons": {"tap -1": 125}}},
        "latency": {"fixed_pf": {"1": {"screen_ms_per_state": 0.5, "solver_ms_per_state": 2.4, "states": 1}}},
        "e1_controller_style": {"summary": {"runs": 4, "speedup_vs_solve_all": 3.0, "speedup_vs_cost_order": 1.2,
                                            "same_choice_as_solve_all": 4, "false_rejections": 1, "overrules": 0}},
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
    assert {g["name"] for g in st["gates"]} == {"voltage_mae_v", "voltage_p99_v"} and not all(g["passed"] for g in st["gates"])
    assert {(s["rule"], s["split"]) for s in st["screening"]} >= {("up_2005", "boundary"), ("pm10", "held_out_tap_mode")}
    assert st["out_of_range"] == [{"kind": "tap_negative", "states": 250, "unsupported": 250}]
    assert st["latency"][0]["solver_ms_per_state"] == 2.4
    assert st["e1"]["speedup_vs_solve_all"] == 3.0 and st["e2"]["skipped_candidates"] == 3
    assert st["states"]["train"] == 10 and st["states"]["boundary_test"] == 20
    assert st["guard_v"] == [1.4, 1.1] and st["guard_loading_pts"] == [1.5, 1.2] and st["shipped_round"] == 2
    assert {(r["round"], r["rule"]) for r in st["rounds"]} == {(1, "up_2005"), (1, "pm10"), (2, "up_2005"), (2, "pm10")}
    assert len(body["disagreements"]["examples"]) <= 12 and body["disagreements"]["counts"][0]["rows"] == 30
    assert "simulated" in body["provenance"]


def test_a_section_not_run_is_null_not_invented(tmp_path):
    _write_reports(tmp_path, e2=False)
    st = _client(tmp_path).get("/surrogate").json()["streets"][0]
    assert st["e2"] is None


def test_all_disagreements_are_available(tmp_path):
    _write_reports(tmp_path)
    body = _client(tmp_path).get("/surrogate/disagreements").json()
    assert len(body["examples"]) == 30
