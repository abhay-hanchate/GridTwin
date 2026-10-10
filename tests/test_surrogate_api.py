"""The screening contract with Addition 1: supported states get a guarded prediction, everything else goes to the solver.

A tiny ridge artifact is trained here on a few solver-labelled families, so these tests need no committed model.
"""
import json
import logging
import math
import warnings
from dataclasses import replace

import numpy as np
import pytest

from backend.v2 import compute
from engine.fixes import switching
from ml.surrogate import artifact, generate, schema, train
from ml.surrogate.api import OperatingState, Screen, load_screener
from ml.surrogate.dataset import Split
from ml.surrogate.teacher import Labels, StateArrays

warnings.filterwarnings("ignore")
STREET = "rural_weak_63"


def _split(net, fams):
    parts = [generate.run_family(net, f, n_scenarios=1, boundary_share=0.2) for f in fams]
    return Split(StateArrays.concat([p["states"] for p in parts]), Labels.concat([p["labels"] for p in parts]),
                 np.concatenate([p["boundary"] for p in parts]), np.concatenate([p["boundary_kind"] for p in parts]),
                 np.concatenate([np.full(len(p["boundary"]), p["family"]["id"]) for p in parts]),
                 np.concatenate([p["step"] for p in parts]))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    net = compute.network(STREET)
    fams = generate.families(STREET)
    pick = lambda split, mode: next(f for f in fams if f.split == split and f.mode == mode)  # noqa: E731
    as_built = dict(layout="planning:1.0", tap=0)
    tr = _split(net, [replace(pick("train", "fixed_pf"), **as_built, topology=0),
                      replace(pick("train", "volt_var"), **as_built, topology=0),
                      replace(pick("train", "fixed_pf"), **as_built, topology=1, seed=11)])
    tu = _split(net, [replace(pick("tune", "fixed_pf"), **as_built, topology=0)])
    cal = _split(net, [replace(pick("calibrate", "fixed_pf"), **as_built, topology=0)])
    d_tr, d_tu, d_cal = (train.prepare(s, STREET) for s in (tr, tu, cal))
    model, _ = train.fit_ridge(d_tr, d_tu)
    guard = {"danger": [0.002, 0.002, 1.0, 1.0, 0.1, 1.0, 1.0], "optimistic": [0.002, 0.002, 1.0, 1.0, 0.1, 1.0, 1.0],
             "alpha": 0.005}
    nov = train.fit_novelty(d_tr, d_cal)
    nov.threshold = float(nov.distance(d_tr.x).max()) * 1.5          # generous: most tests here are not about novelty
    root = tmp_path_factory.mktemp("models")
    artifact.write(root, STREET, model, None, guard, d_tr, net, novelty=nov, extra={"test": True})
    return root, net, tr


def _state(net, split, i, **changes):
    s = split.states
    layout = schema.topologies(net)[int(s.topology[i])]
    base = dict(network_id=STREET, line_ends=tuple(map(tuple, schema.line_ends(layout))), load_kw=s.load_kw[i],
                pv_kw=s.pv_kw[i], upstream_pu=float(s.upstream_pu[i]), battery_kw=float(s.battery_kw[i]),
                battery_node=int(s.battery_node[i]) if s.battery_kw[i] else None, tap_pos=int(s.tap_pos[i]),
                inverter_mode=schema.MODES[int(s.mode[i])], pv_kwp=s.pv_kwp[i])
    base.update(changes)
    return OperatingState(**base)


def _row(tr, topology=0, mode=0, battery=None):
    s = tr.states
    ok = (s.topology == topology) & (s.mode == mode) & ~tr.boundary
    if battery is not None:
        ok &= (s.battery_kw != 0) == battery
    return int(np.flatnonzero(ok)[0])


def test_no_artifact_means_no_screener(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert load_screener(tmp_path) is None
    assert "no surrogate artifact" in caplog.text


def test_a_tampered_artifact_is_refused(built, tmp_path, caplog):
    root, _, _ = built
    import shutil
    shutil.copytree(root, tmp_path / "m")
    path = tmp_path / "m" / STREET / "model.npz"
    path.write_bytes(path.read_bytes()[:-10] + b"0123456789")
    with caplog.at_level(logging.WARNING):
        assert load_screener(tmp_path / "m") is None
    assert "sha256" in caplog.text


def test_a_changed_solver_is_refused(built, tmp_path, caplog):
    root, _, _ = built
    import shutil
    shutil.copytree(root, tmp_path / "m")
    mpath = tmp_path / "m" / STREET / "manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest["solver_hash"] = "0" * 16
    mpath.write_text(json.dumps(manifest))
    with caplog.at_level(logging.WARNING):
        assert load_screener(tmp_path / "m") is None
    assert "solver" in caplog.text


def test_supported_states_get_a_guarded_prediction_with_the_extras(built):
    root, net, tr = built
    screener = load_screener(root)
    rows = [_row(tr, battery=False), _row(tr, battery=True), _row(tr, topology=1)]
    states = [_state(net, tr, i) for i in rows]
    out = screener.screen(states)
    assert all(isinstance(s, Screen) and s.status == "supported" for s in out), [s.reason for s in out]
    detail = screener.screen_detail(states)
    assert np.all(detail["guarded"][:, 0] >= detail["point"][:, 0]) and np.all(detail["guarded"][:, 1] <= detail["point"][:, 1])
    assert out[0].v_max_pu == pytest.approx(detail["guarded"][0, 0])
    assert all(math.isfinite(s.vuf_pct) and math.isfinite(s.neutral_a) and math.isfinite(s.trafo_p_kw) for s in out)


def test_the_rule_and_a_vuf_limit_decide_what_risky_means(built):
    root, net, tr = built
    screener = load_screener(root)
    s = _state(net, tr, _row(tr, battery=False), upstream_pu=1.075, pv_kw=np.zeros(net.n_homes))
    strict, loose = screener.screen([s], rule="up_2005")[0], screener.screen([s], rule="pm10")[0]
    assert strict.status == loose.status == "supported"
    assert strict.risky and strict.v_max_pu > 1.06
    assert not loose.risky and loose.v_max_pu < 1.10
    assert screener.screen([s], rule="pm10", vuf_limit=0.0)[0].risky        # any unbalance breaks a zero limit


@pytest.mark.parametrize("change, reason", [
    ("street", "no surrogate"), ("layout", "layout"), ("phases", "phase map"), ("ambient", "ambient"),
    ("mode", "inverter mode"), ("battery_node", "battery"), ("tap", "tap"), ("load", "outside the trained range"),
    ("pv_over_kwp", "installed"), ("shape", "homes"), ("nan", "finite"), ("novel", "unlike")])
def test_anything_outside_the_support_goes_to_the_solver(built, change, reason):
    root, net, tr = built
    screener = load_screener(root)
    sm = screener.models[STREET]
    s = _state(net, tr, _row(tr, battery=False))
    switched = switching.apply(net, switching.candidates(net)[schema.N_SWITCHED])          # not a trained layout
    other = next(int(n) for n in net.house_node if int(n) not in schema.battery_nodes(STREET))
    if change == "novel":
        sm.novelty.threshold = float(sm.novelty.distance(sm.check(s)[1][None])[0]) * 0.5   # this state now counts as far
    changed = {
        "street": dict(network_id="benchmark_250"),
        "layout": dict(line_ends=tuple(map(tuple, schema.line_ends(switched)))),
        "phases": dict(house_phase=tuple(int(p) for p in np.roll(net.house_phase, 1))),
        "ambient": dict(ambient_c=35.0),
        "mode": dict(inverter_mode="constant_q"),
        "battery_node": dict(battery_kw=10.0, battery_node=other),
        "tap": dict(tap_pos=-1),
        "load": dict(load_kw=s.load_kw * 4 + 5),
        "pv_over_kwp": dict(pv_kw=s.pv_kwp + 1.0),
        "shape": dict(load_kw=s.load_kw[:-1]),
        "nan": dict(upstream_pu=float("nan")),
        "novel": {},
    }[change]
    out = screener.screen([replace(s, **changed)])[0]
    assert out.status == "unsupported" and reason in out.reason and out.risky
    assert np.isnan(out.v_max_pu)


def test_a_changed_street_definition_is_unsupported(built, tmp_path):
    root, net, tr = built
    import shutil
    shutil.copytree(root, tmp_path / "m")
    mpath = tmp_path / "m" / STREET / "manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest["street_hash"] = "f" * 16
    mpath.write_text(json.dumps(manifest))
    out = load_screener(tmp_path / "m").screen([_state(net, tr, 0)])[0]
    assert out.status == "unsupported" and "street" in out.reason


def test_mixed_batches_keep_their_order(built):
    root, net, tr = built
    screener = load_screener(root)
    i = _row(tr, battery=False)
    out = screener.screen([_state(net, tr, i), _state(net, tr, i, tap_pos=-2), _state(net, tr, i)])
    assert [s.status for s in out] == ["supported", "unsupported", "supported"]


def test_default_solar_sizes_are_the_street_as_built(built):
    root, net, tr = built
    screener = load_screener(root)
    i = _row(tr, battery=False)
    a = screener.screen([_state(net, tr, i)])[0]
    b = screener.screen([_state(net, tr, i, pv_kwp=None)])[0]
    assert a.status == b.status == "supported" and a.v_max_pu == pytest.approx(b.v_max_pu)
