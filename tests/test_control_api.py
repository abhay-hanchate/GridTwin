"""The Addition 1 API: the precomputed demonstration runs and custom replays as jobs."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings
from control import replay as replay_mod


def _client(tmp_path, **kw):
    (tmp_path / "control").mkdir(exist_ok=True)
    run = {"config": {"run_id": "forecast_error", "title": "t"}, "records": [], "summary": {"unsafe_steps": 0}}
    (tmp_path / "control" / "forecast_error.json").write_text(json.dumps(run))
    (tmp_path / "control" / "index.json").write_text(json.dumps({"forecast_error": {"title": "t", "summary": {}}}))
    (tmp_path / "control" / "near_limit.json").write_text(json.dumps({"rows": []}))
    return TestClient(create_app(Settings(code_version="c1", results_dir=tmp_path, **kw)), raise_server_exceptions=False)


def test_runs_list_and_one_run(tmp_path):
    c = _client(tmp_path)
    body = c.get("/control/runs").json()
    assert "forecast_error" in body["runs"] and body["near_limit"] == {"rows": []}
    assert c.get("/control/runs/forecast_error").json()["config"]["run_id"] == "forecast_error"
    r = c.get("/control/runs/nope")
    assert r.status_code == 404 and "forecast_error" in r.json()["error"]["details"]["runs"]


def test_a_custom_replay_runs_as_a_job_with_validated_overrides(tmp_path, monkeypatch):
    seen = {}

    class Fake:
        def to_dict(self):
            return {"config": seen["cfg"], "summary": {"unsafe_steps": 0}}

    def fake_run(cfg):
        seen["cfg"] = cfg.to_dict()
        return Fake()
    monkeypatch.setattr(replay_mod, "run", fake_run)
    c = _client(tmp_path)
    r = c.post("/control/replay", json={"fixture": "battery_saturation", "soc_start": 0.6, "curtail": False})
    assert r.status_code == 202
    for _ in range(100):
        body = c.get(f"/jobs/{r.json()['job_id']}").json()
        if body["status"] == "done":
            break
        time.sleep(0.05)
    cfg = body["result"]["config"]
    assert cfg["soc_start"] == 0.6 and cfg["curtail"] is False and cfg["run_id"] == "battery_saturation_custom"
    assert c.post("/control/replay", json={"fixture": "nope"}).status_code == 404
    assert c.post("/control/replay", json={"fixture": "forecast_error", "soc_start": 1.5}).status_code == 422


@pytest.mark.parametrize("path", ["/control/replay"])
def test_offline_mode_refuses_a_new_replay(tmp_path, path):
    c = _client(tmp_path, offline=True)
    assert c.post(path, json={"fixture": "forecast_error"}).status_code == 503
    assert c.get("/control/runs").status_code == 200                      # precomputed runs still served
