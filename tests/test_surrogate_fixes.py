"""Requirement 2.3 on the existing fix tournament: candidates become operating states, the screen sorts them, the solver
still decides every outcome that is shown."""
import warnings

import numpy as np
import pytest
from test_surrogate_api import built  # noqa: F401  (module fixture: a tiny ridge artifact for rural_weak_63)

from backend.v2 import compute
from engine.fixes import catalog
from engine.fixes.base import Candidate
from engine.inverters import VoltVarCurve
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch
from ml.surrogate import fixes, schema
from ml.surrogate.api import load_screener
from ml.surrogate.teacher import StateArrays, solve_states

warnings.filterwarnings("ignore")
STREET = "rural_weak_63"
RULE = compute.rule("pm10")


@pytest.fixture(scope="module")
def scn():
    net = compute.network(STREET)
    full = compute.scenarios("2025-06-10", net, n=4)
    return DayScenarioBatch(full.t, full.load_kw[:2], full.pv_per_kwp[:2], full.upstream_pu[:2], full.load_pf, full.labels[:2])


def test_candidate_states_reproduce_the_day_solver(scn):
    net = compute.network(STREET)
    lim = np.full((96, net.n_homes), 0.5)
    for controls in (Controls(tap_pos=1, curtail_keep=0.8), Controls(export_limit_kw=lim), Controls(volt_var=VoltVarCurve())):
        cand = Candidate("c", "c", "test", net, controls)
        states, reason = fixes.candidate_states(cand, scn, STREET)
        assert reason == "" and len(states) == 2 * 96
        arr = StateArrays(np.stack([s.load_kw for s in states]), np.stack([s.pv_kw for s in states]),
                          np.stack([s.pv_kwp for s in states]), np.array([s.upstream_pu for s in states]),
                          np.zeros(len(states)), np.array([s.tap_pos for s in states]),
                          np.array([schema.MODES.index(s.inverter_mode) for s in states]))
        got = solve_states(net, arr, battery_node=schema.battery_node(STREET))
        ref = DaySolver(net).solve(scn, controls)
        np.testing.assert_allclose(got.u_pu, ref.u_pu.reshape(got.u_pu.shape), atol=2e-4)


@pytest.mark.parametrize("make, reason", [
    (lambda n: Candidate("b", "b", "battery", n, battery=BatterySpec(30, 60, 26)), "battery droop"),
    (lambda n: Candidate("f", "f", "inverter", n, Controls(pf_fixed=0.9)), "power factor"),
    (lambda n: Candidate("s", "s", "inverter", n, Controls(inverter_s_factor=1.1)), "inverter rating")])
def test_candidates_the_screen_cannot_describe_are_unsupported(scn, make, reason):
    states, why = fixes.candidate_states(make(compute.network(STREET)), scn, STREET)
    assert states is None and reason in why


def test_phase_moves_and_switching_are_described_but_refused_by_the_screener(built, scn):  # noqa: F811
    from engine.fixes import switching
    root, net, _ = built
    screener = load_screener(root)
    switched = next(n for rec in switching.candidates(net) if (n := switching.apply(net, rec)).is_radial())
    for cand, reason in ((Candidate("p", "p", "phase", net.with_phases(np.roll(net.house_phase, 1))), "phase map"),
                         (Candidate("s", "s", "switching", switched), "layout")):
        states, why = fixes.candidate_states(cand, scn, STREET)
        assert why == ""
        screens = screener.screen(states, RULE)
        assert all(s.status == "unsupported" and reason in s.reason for s in screens)


def test_assisted_tournament_only_skips_clearly_unsafe_and_verifies_the_rest(built, scn):  # noqa: F811
    root, net, _ = built
    screener = load_screener(root)
    cands = catalog.build(net, scn, RULE, include_battery=False, include_switching=False)[:6]
    out = fixes.assisted_tournament(net, scn, RULE, screener, candidates=cands)
    rows = {r["id"]: r for r in out["candidates"]}
    assert set(rows) == {c.id for c in cands}
    for r in rows.values():
        if r["skipped"]:
            assert r["screen"]["clearly_unsafe_states"] > 0 and r["verified"] is None
        else:
            assert r["verified"] in (True, False)                  # the solver's verdict, not the screen's
    assert all(rows[i]["verified"] for i in out["safe_ranked"])
    assert out["timing"]["screen_s"] >= 0 and out["timing"]["solver_s"] >= 0
