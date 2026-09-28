from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_and_scenarios():
    assert client.get("/api/health").json() == {"status": "ok"}
    ids = [s["id"] for s in client.get("/api/scenarios").json()]
    assert ids == ["S1", "S2", "S3", "S4", "S5"]


def test_run_contract():
    r = client.get("/api/run", params={"scenario": "S4"}).json()
    assert len(r["steps"]) == 96
    for key in ("max_vm_pu", "violation_steps", "violation_steps_from_solar"):
        assert key in r["summary"]
    assert set(r["provenance"]) == {"load", "voltage", "pv", "grid"}


def test_actions_contract():
    r = client.get("/api/actions", params={"scenario": "S4"}).json()
    assert r["verdict"]["safe_action_found"] is True
    assert r["actions"][0]["rank"] == 1 and r["actions"][0]["remaining_violation_steps"] == 0


def test_strict_band_has_no_safe_action():
    r = client.get("/api/actions", params={"scenario": "S5"}).json()
    assert r["verdict"]["safe_action_found"] is False


def test_forecast_bands_are_ordered():
    pts = client.get("/api/forecast", params={"target": "solar"}).json()["points"]
    assert len(pts) == 96
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in pts)


def test_summary_shows_solar_making_it_worse():
    rows = {r["id"]: r for r in client.get("/api/summary").json()}
    assert rows["S4"]["violation_steps"] > rows["S1"]["violation_steps"]
    assert "steps" not in rows["S4"]


def test_unknown_scenario_is_404():
    assert client.get("/api/run", params={"scenario": "S9"}).status_code == 404


def test_fix_simulation_shows_the_fix_working():
    r = client.get("/api/fix-sim", params={"scenario": "S4", "action": "tap1_volt_var"}).json()
    assert len(r["times"]) == 96 and len(r["before"]["vm"][0]) == len(r["bus_ids"])
    assert r["before"]["summary"]["violation_steps"] > 0
    assert r["after"]["summary"]["violation_steps"] == 0
    assert r["after"]["steps"][44]["inverter_kvar"] > 0      # inverters absorb reactive power at 11:00


def test_unknown_fix_is_404():
    assert client.get("/api/fix-sim", params={"action": "magic"}).status_code == 404


def test_forecast_simulation_predicts_the_real_day():
    r = client.get("/api/forecast-sim").json()
    predicted = r["before"]["summary"]["violation_steps"]
    actual = r["after"]["summary"]["violation_steps"]
    assert abs(predicted - actual) <= 4
