import json

from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings
from scripts.evaluate import STATUSES, evaluate, g8, proof_markdown


def _write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def test_every_gate_is_present_and_missing_inputs_say_missing(tmp_path):
    r = evaluate(tmp_path, skip_parity=True)
    assert [g["gate"] for g in r["gates"]] == ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]
    assert all(g["status"] in STATUSES for g in r["gates"])
    assert {g["gate"]: g["status"] for g in r["gates"]}["G4"] == "missing"
    assert r["gates"][0]["status"] == "not_run" and sum(r["summary"].values()) == 8


def test_a_failed_gate_is_written_as_failed(tmp_path):
    _write(tmp_path, "ml/reports/demand_v2.json", {"gate_g4": {"skill_vs_best_baseline": 0.084, "coverage": 0.833, "passed": False}})
    for rule, skill in (("pm10", 0.51), ("up_2005", -1.9)):
        _write(tmp_path, f"data/results/risk_calibration_{rule}.json", _calibration(skill))
    r = evaluate(tmp_path, skip_parity=True)
    gates = {g["gate"]: g for g in r["gates"]}
    assert gates["G4"]["status"] == "fail" and gates["G4"]["passed"] is False
    assert gates["G8"]["status"] == "fail" and gates["G8"]["measured"]["up_2005"]["brier_skill_calibrated"] == -1.9
    assert "**fail**" in proof_markdown(r)


def _calibration(skill: float, district_skill: dict | None = None) -> dict:
    by = {d: {"days": 40, "observed_unsafe_share": 0.5, "skill_calibrated": v}
          for d, v in (district_skill or {"mathura": skill, "bareilly": skill}).items()}
    return {"reliable": skill > 0, "held_out_test": {"days": 80, "observed_unsafe_share": 0.5, "brier_calibrated": 0.1,
                                                     "brier_base_rate": 0.2, "skill_raw": skill,
                                                     "skill_calibrated": skill, "by_district": by}}


def test_g8_passes_only_when_every_rule_has_skill_and_names_weak_districts(tmp_path):
    _write(tmp_path, "data/results/risk_calibration_pm10.json", _calibration(0.5))
    _write(tmp_path, "data/results/risk_calibration_up_2005.json", _calibration(0.4, {"mathura": -3.9, "bareilly": 0.36}))
    g = g8(tmp_path)
    assert g["status"] == "pass" and "mathura under up_2005" in g["note"]
    _write(tmp_path, "data/results/risk_calibration_up_2005.json", _calibration(-0.1))
    assert g8(tmp_path)["status"] == "fail"


def test_g8_is_missing_for_a_single_district_calibration_file(tmp_path):
    for rule in ("pm10", "up_2005"):
        _write(tmp_path, f"data/results/risk_calibration_{rule}.json", {"reliable": True, "held_out_test": {}})
    assert g8(tmp_path)["status"] == "missing"


def test_licence_and_plant_gates_follow_the_recorded_decisions(tmp_path):
    _write(tmp_path, "docs/DATA_SOURCES.md", "Open-Meteo's free API allows non-commercial use only")
    _write(tmp_path, "docs/DECISIONS.md", "the outcome is **(b)**: the calibration script is not run")
    gates = {g["gate"]: g for g in evaluate(tmp_path, skip_parity=True)["gates"]}
    assert gates["G6"]["status"] == "conditional" and gates["G7"]["status"] == "not_run"


def test_results_route_serves_the_file_or_503(tmp_path):
    c = TestClient(create_app(Settings(code_version="e1", results_dir=tmp_path)), raise_server_exceptions=False)
    assert c.get("/results").status_code == 503
    (tmp_path / "results.json").write_text(json.dumps({"gates": []}))
    assert c.get("/results").json() == {"gates": []}
