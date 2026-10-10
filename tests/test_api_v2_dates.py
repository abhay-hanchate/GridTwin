"""F6: a date the API cannot forecast is refused at once (404 with the valid ranges), never accepted as a job."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.v2 import compute
from backend.v2.app import create_app
from backend.v2.live_inputs import today_ist
from backend.v2.settings import Settings
from ml.live_forecast import LiveForecastError

GET_ROUTES = ("/risk", "/fixes", "/street", "/simulate", "/headroom", "/hosting", "/meter-sites", "/rx-map",
              "/transformers", "/report")


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(code_version="d1", results_dir=tmp_path)), raise_server_exceptions=False)


def _bad_dates() -> list[str]:
    s = Settings()
    return ["2024-05-15",                                                   # before the archive
            "2026-03-01" if today_ist().isoformat() > "2026-03-01" else "2024-12-31",   # after it, before today
            (today_ist() + timedelta(days=s.live_horizon_days + 1)).isoformat()]  # beyond the live forecast


@pytest.mark.parametrize("route", GET_ROUTES)
def test_dates_outside_the_archive_and_the_live_horizon_are_404_without_a_job(client, route):
    for day in _bad_dates():
        r = client.get(route, params={"date": day})
        assert r.status_code == 404, (route, day, r.status_code)
        err = r.json()["error"]
        assert err["code"] == "not_found" and day in err["message"]
        assert err["details"]["archive"] == {"first": "2025-01-01", "last": "2025-12-31"}
        assert "live" in err["details"]


def test_post_routes_refuse_the_same_dates(client):
    day = _bad_dates()[0]
    r = client.post("/connection-check", json={"date": day, "node": 1, "kw": 3})
    assert r.status_code == 404 and day in r.json()["error"]["message"]
    r = client.post("/whatif", json={"date": day})
    assert r.status_code == 404 and day in r.json()["error"]["message"]


def test_valid_dates_still_start_a_job(client, monkeypatch):
    monkeypatch.setattr(compute, "risk_payload", lambda *a, **k: {"ok": True})
    for day in ("2025-01-01", "2025-12-31", (today_ist() + timedelta(days=1)).isoformat()):
        assert client.get("/risk", params={"date": day}).status_code in (200, 202), day


def test_a_live_forecast_failure_is_a_503(client, monkeypatch):
    def boom(*a, **k):
        raise LiveForecastError("Open-Meteo multi-model request failed: 400 Bad Request")
    monkeypatch.setattr(compute, "connection_payload", boom)
    r = client.post("/connection-check", json={"date": "2025-05-15", "node": 1, "kw": 3})
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
    assert "live forecast" in r.json()["error"]["message"]
