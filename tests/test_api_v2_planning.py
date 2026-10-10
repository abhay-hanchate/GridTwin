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
    assert "regulatory_status" in body and set(body["evidence"]["per_phase_worsened_steps"]) == {"A", "B", "C"}
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


def test_hosting_runs_as_a_job_and_reports_both_cases(client, monkeypatch):
    monkeypatch.setattr(compute, "hosting_payload", lambda d, n, r: {"without_fix": {}, "with_volt_var": {}, "rule": r})
    r = client.get("/hosting", params={"date": "2025-05-15", "rule": "6"})
    assert r.status_code == 202
    for _ in range(100):
        body = client.get(f"/jobs/{r.json()['job_id']}").json()
        if body["status"] == "done":
            break
        time.sleep(0.05)
    assert body["result"]["rule"] == "up_2005" and set(body["result"]) >= {"without_fix", "with_volt_var"}


def test_planning_defaults_to_its_own_precomputed_date(tmp_path, monkeypatch):
    import json
    from backend.v2.app import create_app
    from backend.v2.settings import Settings
    (tmp_path / "v2").mkdir()
    (tmp_path / "v2" / "index.json").write_text(json.dumps({"entries": [
        {"route": "risk", "date": "2025-11-19"}, {"route": "headroom", "date": "2025-05-15"},
        {"route": "hosting", "date": "2025-05-15"}]}))
    seen = []
    monkeypatch.setattr(compute, "headroom_payload", lambda d, n, r, a: seen.append(("headroom", d)) or {})
    monkeypatch.setattr(compute, "hosting_payload", lambda d, n, r: seen.append(("hosting", d)) or {})
    c = TestClient(create_app(Settings(code_version="d1", results_dir=tmp_path)), raise_server_exceptions=False)
    for route in ("/headroom", "/hosting"):
        job = c.get(route).json()
        for _ in range(100):
            if c.get(f"/jobs/{job['job_id']}").json()["status"] == "done":
                break
            time.sleep(0.05)
    assert sorted(seen) == [("headroom", "2025-05-15"), ("hosting", "2025-05-15")]      # not the latest risk date


def _job_result(client, response):
    assert response.status_code == 202, response.text
    for _ in range(100):
        body = client.get(f"/jobs/{response.json()['job_id']}").json()
        if body["status"] == "done":
            return body["result"]
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_meter_sites_and_rx_map_run_as_jobs_on_the_chosen_street(client, monkeypatch):
    monkeypatch.setattr(compute, "meter_sites_payload", lambda d, n, r, a: {"network": n, "rule": r, "sites": []})
    monkeypatch.setattr(compute, "rx_map_payload", lambda d, n, r, a: {"network": n, "cells": []})
    out = _job_result(client, client.get("/meter-sites", params={"date": "2025-05-15", "network": "rural_weak_63"}))
    assert out["network"] == "rural_weak_63"
    assert _job_result(client, client.get("/rx-map", params={"date": "2025-05-15"}))["network"] == "benchmark_250"
    assert client.get("/meter-sites", params={"network": "nope"}).status_code == 404
    assert client.get("/rx-map", params={"adoption": -1}).status_code == 422


def test_transformers_rank_the_whole_portfolio_without_a_network(client, monkeypatch):
    monkeypatch.setattr(compute, "transformers_payload", lambda d, r, a: {"rule": r, "transformers": [], "adoption": a})
    out = _job_result(client, client.get("/transformers", params={"date": "2025-05-15", "rule": "6", "adoption": 0.4}))
    assert out == {"rule": "up_2005", "transformers": [], "adoption": 0.4}


def test_planning_extras_on_the_real_street():
    meters = compute.meter_sites_payload("2025-05-15", "benchmark_250", "pm10")
    assert 0 < len(meters["sites"]) <= compute.METER_SITES_SHOWN <= meters["n_candidates"]
    assert [s["score"] for s in meters["sites"]] == sorted((s["score"] for s in meters["sites"]), reverse=True)
    rx = compute.rx_map_payload("2025-05-15", "benchmark_250", "pm10")
    assert len(rx["cells"]) == 16
    # Volt/VAR lowers the peak on every wire with a resistance-to-reactance ratio up to about 5. On very resistive,
    # low-reactance wires (R/X 6.3, the extreme corner) absorbing VARs adds current and loss and can raise the peak
    # slightly (+0.4 V on 15 May 2025); the page shows that as a plus sign.
    assert all(c["peak_v_volt_var"] <= c["peak_v_without"] + 0.05 for c in rx["cells"] if c["r_over_x"] <= 5)
    assert all(c["peak_v_volt_var"] <= c["peak_v_without"] + 1.0 for c in rx["cells"])
    base = next(c for c in rx["cells"] if c["r_scale"] == 1 and c["x_scale"] == 1)
    assert base["peak_v_volt_var"] < base["peak_v_without"]
