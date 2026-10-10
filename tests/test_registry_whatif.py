import time
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.v2 import routes_whatif
from backend.v2.app import create_app
from backend.v2.settings import Settings
from engine.archetypes import build
from engine.dayinputs import scenarios_from_legacy
from engine.powerflow import day_inputs
from engine.registry import REGISTRY, catalog
from engine.types import Controls

warnings.filterwarnings("ignore")


def test_catalog_lists_changes_and_fixes_with_parameter_schemas():
    entries = {e["id"]: e for e in catalog()}
    assert {"change.panel_size", "change.upstream_shift", "change.ev_charging", "change.heatwave",
            "fix.tap", "fix.volt_var", "fix.volt_watt", "fix.curtail", "fix.battery"} <= set(entries)
    tap = entries["fix.tap"]["params"]["properties"]["tap_pos"]
    assert (tap["minimum"], tap["maximum"]) == (-2, 2)


def test_changes_modify_the_street_or_the_day():
    net = build("benchmark_250")
    scn = scenarios_from_legacy(day_inputs("2019-05-15"), net)
    e = REGISTRY["change.ev_charging"]
    _, s2 = e.fn(net, scn, e.params(share_of_homes=0.5, kw=3.3, start_hour=19, hours=4))
    added = (s2.load_kw - scn.load_kw)[0]
    assert added[19 * 4].max() == pytest.approx(3.3) and added[12 * 4].max() == 0      # evening only
    assert (added[19 * 4] > 0).sum() == round(0.5 * net.n_homes)
    e = REGISTRY["change.panel_size"]
    n2, _ = e.fn(net, scn, e.params(kwp_per_home=5))
    assert set(np.unique(n2.house_kwp)) <= {0.0, 5.0}
    e = REGISTRY["fix.tap"]
    assert e.fn(Controls(), e.params(tap_pos=2)).tap_pos == 2


@pytest.fixture
def client(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(routes_whatif, "whatif_payload", lambda **spec: calls.append(spec) or {"spec": spec})
    return TestClient(create_app(Settings(code_version="w1", results_dir=tmp_path)), raise_server_exceptions=False), calls


def _done(c, r):
    if r.status_code == 200:
        return r.json()
    for _ in range(100):
        body = c.get(f"/jobs/{r.json()['job_id']}").json()
        if body["status"] in ("done", "failed"):
            return body["result"]
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_whatif_validates_and_normalises_the_spec(client):
    c, calls = client
    spec = {"date": "2025-05-15", "rule": "6", "changes": [{"id": "change.heatwave", "params": {"load_factor": 1.5}}],
            "fixes": [{"id": "fix.tap"}]}
    out = _done(c, c.post("/whatif", json=spec))["spec"]
    assert out["rule"] == "up_2005" and out["fixes"] == [{"id": "fix.tap", "params": {"tap_pos": 1}}]   # defaults filled
    _done(c, c.post("/whatif", json=spec))
    assert len(calls) == 1                                                # the same spec twice runs once


def test_whatif_rejects_unknown_ids_and_bad_parameters(client):
    c, _ = client
    r = c.post("/whatif", json={"fixes": [{"id": "fix.magic"}]})
    assert r.status_code == 404 and "fix.tap" in r.json()["error"]["details"]["valid"]
    r = c.post("/whatif", json={"changes": [{"id": "fix.tap"}]})                         # a fix is not a change
    assert r.status_code == 404
    r = c.post("/whatif", json={"fixes": [{"id": "fix.tap", "params": {"tap_pos": 9}}]})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"][0]["loc"] == ["tap_pos"]


@pytest.mark.slow
def test_real_whatif_compares_before_and_after():
    out = routes_whatif.whatif_payload(date="2025-05-15", network="benchmark_250", rule="pm10", adoption=1.0,
                                       changes=[{"id": "change.upstream_shift", "params": {"shift_pct": -1}}],
                                       fixes=[{"id": "fix.volt_var", "params": {}}])
    assert len(out["t"]) == 96 and len(out["before"]["node_max_v"]) == 96
    assert len(out["before"]["node_max_v"][0]) == len(out["nodes"])
    assert out["after"]["summary"]["max_vm_pu"] < out["before"]["summary"]["max_vm_pu"]


def test_nightly_and_route_compute_the_same_whatif_key(tmp_path):
    from backend.v2.jobs import JobStore
    from backend.v2.routes_whatif import WhatIf, normalise
    s = Settings(code_version="k1", results_dir=tmp_path)
    store = JobStore(tmp_path)
    a = normalise(WhatIf(date="2025-05-15", rule="10", fixes=[{"id": "fix.tap"}]), s, store)[1]
    b = normalise(WhatIf(date="2025-05-15", rule="pm10", fixes=[{"id": "fix.tap", "params": {"tap_pos": 1}}]), s, store)[1]
    assert a == b                                                   # alias and filled-in defaults give one key


def test_a_change_is_compared_with_todays_street():
    # Evening EV charging must show up against the street as it is today, even with no fix chosen.
    out = routes_whatif.whatif_payload(date="2025-05-15", network="benchmark_250", rule="pm10", fixes=[],
                                       changes=[{"id": "change.ev_charging", "params": {"share_of_homes": 0.3, "kw": 3.3}}])
    assert out["before"] == out["after"]                         # no fix: the changed street, twice
    today, changed = out["today"]["summary"], out["before"]["summary"]
    assert changed["max_trafo_loading_pct"] > today["max_trafo_loading_pct"]
    assert changed["min_vm_pu"] < today["min_vm_pu"]
