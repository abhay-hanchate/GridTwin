import time

import pytest
from fastapi.testclient import TestClient

from backend.v2 import compute
from backend.v2.app import create_app
from backend.v2.settings import Settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    app = create_app(Settings(code_version="p1", results_dir=tmp_path_factory.mktemp("res")))
    return TestClient(app, raise_server_exceptions=False)


def test_connection_check_validates_the_request(client):
    assert client.post("/connection-check", json={"node": 65, "kw": 500}).status_code == 422          # kw in (0, 50]
    assert client.post("/connection-check", json={"node": 65, "kw": 5, "phase": "D"}).status_code == 422
    assert client.post("/connection-check", json={"node": 65, "kw": 5, "network": "x"}).status_code == 404


def test_connection_check_gives_a_decision_with_a_phase_and_a_reason(client):
    t = time.perf_counter()
    r = client.post("/connection-check", json={"node": 65, "kw": 5, "rule": "pm10"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] in ("approve", "approve_with_conditions", "refuse") and body["phase"] in ("A", "B", "C")
    assert "regulatory_status" in body and set(body["evidence"]["per_phase_unsafe_steps"]) == {"A", "B", "C"}
    assert body["provenance"]["grid"].startswith("benchmark")
    assert time.perf_counter() - t < 60          # live budget is 5 s once warm; the first call also fits the models


def test_a_node_on_the_11_kv_side_is_a_422_with_the_valid_nodes(client):
    r = client.post("/connection-check", json={"node": 9999, "kw": 3})
    assert r.status_code == 422 and r.json()["error"]["details"]["valid_nodes"]


def test_headroom_runs_as_a_job(client, monkeypatch):
    monkeypatch.setattr(compute, "headroom_payload", lambda *a, **k: {"locations": {}, "adoption": a[3]})
    r = client.get("/headroom", params={"date": "2025-05-15", "adoption": 0.5})
    assert r.status_code == 202
    for _ in range(100):
        body = client.get(f"/jobs/{r.json()['job_id']}").json()
        if body["status"] == "done":
            break
        time.sleep(0.05)
    assert body["result"]["adoption"] == 0.5
    assert client.get("/headroom", params={"adoption": 2}).status_code == 422
