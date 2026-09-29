import json

import pytest
from fastapi.testclient import TestClient

import backend.main as api
from backend.cache import CorruptCacheError, cache_path, load_or_compute

client = TestClient(api.app)


@pytest.mark.parametrize("key", ["../escape", "folder/name", r"folder\name", "name with spaces"])
def test_cache_key_rejects_traversal_and_separators(tmp_path, key):
    with pytest.raises(ValueError):
        cache_path(tmp_path, key)


def test_cache_write_is_valid_json_and_reused(tmp_path):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"value": 7}

    assert load_or_compute(tmp_path, "safe-key", compute) == {"value": 7}
    assert json.loads((tmp_path / "safe-key.json").read_text()) == {"value": 7}
    assert load_or_compute(tmp_path, "safe-key", compute) == {"value": 7}
    assert calls == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_cache_fails_closed(tmp_path):
    (tmp_path / "broken.json").write_text("not json")
    with pytest.raises(CorruptCacheError):
        load_or_compute(tmp_path, "broken", lambda: {"replacement": True})


@pytest.mark.parametrize(
    "path",
    [
        "/api/run?date=../../outside",
        "/api/early-warning?risk=magic",
        "/api/early-warning?band=5",
        "/api/forecast?target=unknown",
    ],
)
def test_invalid_external_parameters_are_rejected(path):
    assert client.get(path).status_code == 422


def test_corrupt_api_cache_returns_service_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "RESULTS_DIR", tmp_path)
    (tmp_path / "run_S4_2019-05-15.json").write_text("not json")
    response = client.get("/api/run", params={"scenario": "S4", "date": "2019-05-15"})
    assert response.status_code == 503
    assert "unreadable" in response.json()["detail"]


def test_readiness_exposes_each_required_artifact():
    response = client.get("/api/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ready", "degraded"}
    assert set(body["files"]) == {
        "solar_forecast", "demand_forecast", "model_metrics", "solar_explainability",
        "solar_model_manifest", "solar_model_p10", "solar_model_p50", "solar_model_p90",
    }


def test_solar_model_report_is_auditable():
    response = client.get("/api/model-report", params={"target": "solar"})
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "solar_p50"
    assert body["features_available_at_issue_time"] is True
    assert len(body["importance"]) == 7
    assert abs(sum(row["gain_normalized"] for row in body["importance"]) - 1.0) < 1e-4
    assert body["limitations"]
