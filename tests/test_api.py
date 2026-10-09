import pytest
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


def test_hosting_capacity_reports_headroom_with_and_without_fix():
    response = client.get("/api/hosting-capacity")

    assert response.status_code == 200
    result = response.json()
    assert result["date"] == "2019-05-15"
    assert result["baseline_unsafe_steps"] == 5
    assert len(result["points"]) == 11
    assert result["capacity"]["without_fix"]["solar_homes"] == 10
    assert result["capacity"]["without_fix"]["found_safe_level"] is True
    assert result["capacity"]["with_fix"]["solar_homes"] == 99
    assert result["capacity"]["with_fix"]["unsafe_steps"] == 0
    assert result["capacity"]["with_fix"]["found_safe_level"] is True


def test_hosting_capacity_rejects_unsupported_voltage_band():
    response = client.get("/api/hosting-capacity", params={"band": "7"})

    assert response.status_code == 422


def test_strict_band_has_no_safe_action():
    r = client.get("/api/actions", params={"scenario": "S5"}).json()
    assert r["verdict"]["safe_action_found"] is False


def test_forecast_bands_are_ordered():
    pts = client.get("/api/forecast", params={"target": "solar"}).json()["points"]
    assert len(pts) == 96
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in pts)


@pytest.mark.parametrize("target", ["wind", "demand-ish"])
def test_forecast_rejects_unknown_target(target):
    response = client.get("/api/forecast", params={"target": target})

    assert response.status_code == 422


@pytest.mark.parametrize("target", ["solar", "demand"])
def test_forecast_returns_404_when_date_is_unavailable(target):
    response = client.get("/api/forecast", params={"target": target, "date": "1900-01-01"})

    assert response.status_code == 404
    assert f"No {target} forecast for 1900-01-01" in response.json()["detail"]


def test_demand_forecast_uses_per_home_units():
    response = client.get("/api/forecast", params={"target": "demand", "date": "2019-11-01"})

    assert response.status_code == 200
    assert response.json()["unit"] == "kW per home"
    assert len(response.json()["points"]) == 96


def test_summary_shows_solar_making_it_worse():
    rows = {r["id"]: r for r in client.get("/api/summary").json()}
    assert rows["S4"]["violation_steps"] > rows["S1"]["violation_steps"]
    assert "steps" not in rows["S4"]


def test_unknown_scenario_is_404():
    assert client.get("/api/run", params={"scenario": "S9"}).status_code == 404


@pytest.mark.parametrize("endpoint", ["/api/run", "/api/actions"])
def test_simulation_returns_422_when_meter_data_is_missing(endpoint):
    response = client.get(endpoint, params={"scenario": "S4", "date": "1900-01-01"})

    assert response.status_code == 422
    assert "No complete meter data for 1900-01-01" in response.json()["detail"]


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


def test_rules_endpoint_lists_sources_and_verification():
    rules = client.get("/api/rules").json()
    ids = [r["id"] for r in rules]
    assert {"pm10", "up_2005"} <= set(ids)
    up = next(r for r in rules if r["id"] == "up_2005")
    assert up["vmin_v"] == 216.2 and up["vmax_v"] == 243.8
    assert up["verification"] == "secondary" and "UPERC" in up["source"]


def test_scenario_s5_names_the_rule():
    scenarios = {s["id"]: s for s in client.get("/api/scenarios").json()}
    assert "UP Supply Code" in scenarios["S5"]["name"] and scenarios["S5"]["band"] == "up_2005"


def test_hosting_capacity_rejects_an_unknown_rule_with_the_valid_ids():
    response = client.get("/api/hosting-capacity", params={"band": "nope"})
    assert response.status_code == 422 and "up_2005" in response.json()["detail"]
