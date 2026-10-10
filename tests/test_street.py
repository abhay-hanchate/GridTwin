import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.v2 import compute
from backend.v2.app import create_app
from backend.v2.settings import Settings
from engine.archetypes import build
from engine.street import layout, line_flows


@pytest.fixture(scope="module")
def net():
    return build("benchmark_250", phases="round_robin")


def test_layout_places_every_node_once_and_orients_lines_away_from_the_transformer(net):
    out = layout(net)
    ids = [n["id"] for n in out["nodes"]]
    assert len(ids) == len(set(ids)) == len(net.lv_nodes)
    x = {n["id"]: n["x"] for n in out["nodes"]}
    assert x[out["root"]] == 0 and all(x[ln["to"]] == x[ln["from"]] + 1 for ln in out["lines"])
    assert len(out["lines"]) == net.n_lines and out["rows"] >= 2


def test_balanced_phases_leave_no_neutral_current_and_one_phase_carries_it_all(net):
    balanced = np.ones((2, net.n_homes))
    flows = line_flows(net, balanced)
    root_lines = [ln["line"] for ln in layout(net)["lines"] if ln["from"] == net.trafo.to_node]
    # what reaches the transformer is every home's net power
    total = flows["phase_kw"][root_lines].sum(axis=(0, 2))
    assert total == pytest.approx([net.n_homes] * 2)
    only_a = np.where(net.house_phase == 0, 1.0, 0.0)[None, :].repeat(2, axis=0)
    f = line_flows(net, only_a)
    i = root_lines[0]
    assert f["neutral_a"][i, 0] == pytest.approx(f["phase_kw"][i, 0, 0] * 1000 / 230)


def test_exporting_homes_reverse_the_flow(net):
    f = line_flows(net, -np.ones((1, net.n_homes)))
    assert (f["phase_kw"].sum(axis=2) <= 0).all()


def test_street_and_calendar_routes(tmp_path, monkeypatch):
    c = TestClient(create_app(Settings(code_version="s1", results_dir=tmp_path)), raise_server_exceptions=False)
    monkeypatch.setattr(compute, "street_payload", lambda d, n, r, f: {"fix": f, "rule": r})
    r = c.get("/street", params={"date": "2025-05-15", "fix": "tap_plus1"})
    assert r.status_code == 202
    for _ in range(100):
        body = c.get(f"/jobs/{r.json()['job_id']}").json()
        if body["status"] == "done":
            break
        time.sleep(0.05)
    assert body["result"]["fix"] == "tap_plus1"
    cal = c.get("/calendar").json()
    assert cal["archive"]["first"] <= cal["archive"]["last"] and "tomorrow" in cal and cal["offline"] is False
