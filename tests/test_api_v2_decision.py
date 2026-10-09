import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.v2 import compute
from backend.v2.app import create_app
from backend.v2.jobs import cache_key
from backend.v2.settings import Settings

CALLS = {"risk": 0}


def _fake_risk(date, network, rule, fix=None, **_):
    CALLS["risk"] += 1
    time.sleep(1.0)
    return {"date": date, "network": network, "rule": rule, "fix": fix, "level": "act", "p_unsafe": [0.5] * 96}


@pytest.fixture
def client(tmp_path, monkeypatch):
    CALLS["risk"] = 0
    monkeypatch.setattr(compute, "risk_payload", _fake_risk)
    app = create_app(Settings(code_version="t1", results_dir=tmp_path))
    return TestClient(app, raise_server_exceptions=False), tmp_path


def _wait(c, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        body = c.get(f"/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_a_miss_starts_one_job_then_the_result_is_cached(client):
    c, _ = client
    r = c.get("/risk", params={"date": "2025-05-15", "rule": "pm10"})
    assert r.status_code == 202 and r.json()["status"] in ("queued", "running")
    shared = c.get("/risk", params={"date": "2025-05-15", "rule": "pm10"}).json()
    assert shared["job_id"] == r.json()["job_id"]                      # identical requests share one job
    done = _wait(c, r.json()["job_id"])
    assert done["status"] == "done" and done["result"]["level"] == "act"
    t = time.perf_counter()
    hit = c.get("/risk", params={"date": "2025-05-15", "rule": "pm10"})
    assert hit.status_code == 200 and hit.json()["p_unsafe"] == [0.5] * 96
    assert time.perf_counter() - t < 0.3 and CALLS["risk"] == 1        # served from cache, computed once


def test_alias_and_rule_id_share_a_cache_entry(client):
    c, _ = client
    _wait(c, c.get("/risk", params={"date": "2025-05-15", "rule": "6"}).json()["job_id"])
    assert c.get("/risk", params={"date": "2025-05-15", "rule": "up_2005"}).status_code == 200


def test_unknown_network_rule_fix_and_job_are_404(client):
    c, _ = client
    assert c.get("/risk", params={"network": "atlantis"}).json()["error"]["details"]["valid"][0] == "benchmark_250"
    assert c.get("/risk", params={"rule": "nope"}).status_code == 404
    assert "tap2_volt_var" in c.get("/risk", params={"fix": "magic"}).json()["error"]["details"]["valid"]
    assert c.get("/jobs/nope").status_code == 404
    assert c.get("/risk", params={"date": "15-05-2025"}).status_code == 422


def test_default_date_is_the_latest_precomputed_one(client):
    c, root = client
    (root / "v2").mkdir(exist_ok=True)
    (root / "v2" / "index.json").write_text(json.dumps({"entries": [
        {"route": "risk", "date": "2025-05-02"}, {"route": "risk", "date": "2025-09-30"}, {"route": "fixes", "date": "2025-12-01"}]}))
    body = _wait(c, c.get("/risk").json()["job_id"])
    assert body["result"]["date"] == "2025-09-30"


def test_offline_mode_serves_only_precomputed_results(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(compute, "risk_payload", lambda *a, **k: calls.append(1) or {})
    c = TestClient(create_app(Settings(code_version="t1", results_dir=tmp_path, offline=True)), raise_server_exceptions=False)
    r = c.get("/risk", params={"date": "2025-05-15", "rule": "pm10"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable" and calls == []
    key = cache_key("risk", "t1", date="2025-05-15", network="benchmark_250", rule="pm10", fix="none")
    (tmp_path / "v2").mkdir(exist_ok=True)
    (tmp_path / "v2" / f"{key}.json").write_text(json.dumps({"level": "watch"}))
    assert c.get("/risk", params={"date": "2025-05-15", "rule": "pm10"}).json() == {"level": "watch"}


def test_a_failing_job_reports_the_message_not_a_trace(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(compute, "fixes_payload", lambda *a, **k: (_ for _ in ()).throw(ValueError("no data for that day")))
    body = _wait(c, c.get("/fixes", params={"date": "2025-05-15"}).json()["job_id"])
    assert body == {"job_id": body["job_id"], "status": "failed", "error": "no data for that day"}


def test_cache_key_changes_with_code_version():
    a = cache_key("risk", "v1", date="2025-05-15", rule="pm10")
    assert a != cache_key("risk", "v2", date="2025-05-15", rule="pm10") and a.startswith("risk_")
    assert a == cache_key("risk", "v1", rule="pm10", date="2025-05-15")       # order-independent


@pytest.mark.slow
def test_real_risk_payload_matches_the_dashboard_shape():
    r = compute.risk_payload("2025-05-15", "benchmark_250", "pm10", n=20)
    assert len(r["p_unsafe"]) == len(r["t"]) == 96 and r["t"][0] == "00:00"
    assert set(r["window_risk"]) == {"15min", "1h", "3h", "24h"}
    assert set(r["shares"]) == {"overvoltage", "undervoltage", "line_overload", "trafo_overload", "solver_failure"}
    import json as _json
    from engine import config
    stored = _json.loads((config.ROOT / "data" / "results" / "risk_calibration_pm10.json").read_text(encoding="utf-8"))
    assert r["thresholds"] == {"watch": 0.2, "act": 0.5} and r["calibration"]["reliable"] is stored["reliable"]
    assert r["level"] in {"ok", "watch", "act"} and set(r["provenance"]) >= {"solar", "demand", "voltage"}


def test_unknown_forecast_date_is_a_404_with_the_range():
    with pytest.raises(compute.ApiError) as err:
        compute.solar_forecast("2019-01-01")
    assert err.value.status == 404 and "2025" in err.value.message


def test_calibration_applies_the_stored_map_and_its_verdict(tmp_path, monkeypatch):
    import json as _json
    from engine import config
    (tmp_path / "data" / "results").mkdir(parents=True)
    (tmp_path / "data" / "results" / "risk_calibration_pm10.json").write_text(_json.dumps(
        {"map": {"x": [0.0, 0.5, 1.0], "y": [0.2, 0.8, 1.0]}, "reliable": True,
         "held_out_test": {"skill_calibrated": 0.12}}))
    monkeypatch.setattr(config, "ROOT", tmp_path)
    cal = compute.calibration("pm10", [0.0, 0.25, 1.0])
    assert cal["calibrated"] == [0.2, 0.5, 1.0] and cal["reliable"] is True and cal["held_out_skill"] == 0.12
    assert compute.calibration("up_2005", [0.3])["reliable"] is False           # no map for this rule
