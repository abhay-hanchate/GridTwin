"""The evidence routes list the brief's files and serve only those."""
from fastapi.testclient import TestClient

from backend.v2.app import create_app

client = TestClient(create_app())


def test_lists_every_group_the_brief_names():
    groups = {g["id"]: g["files"] for g in client.get("/evidence/files").json()["groups"]}
    for name in ("solver_configurations", "generated_state_splits", "surrogate_artifacts", "state_of_charge_traces",
                 "action_logs", "error_latency_results", "final_verification_outputs"):
        assert groups[name], f"no files for {name}"
    assert any(f["path"].endswith("soc_trace.csv") for f in groups["state_of_charge_traces"])


def test_serves_a_listed_file():
    r = client.get("/evidence/file", params={"path": "data/surrogate/splits.json"})
    assert r.status_code == 200 and r.content


def test_refuses_anything_not_listed():
    for path in ("backend/v2/settings.py", "../README.md", "data/surrogate/../../.env", "/etc/passwd"):
        r = client.get("/evidence/file", params={"path": path})
        assert r.status_code == 404
        assert "error" in r.json()
