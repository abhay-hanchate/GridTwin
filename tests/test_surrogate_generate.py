"""Solver-labelled states: family splits that differ in operating conditions, boundary states and out-of-range sets."""
import warnings

import numpy as np
import pytest

from backend.v2 import compute
from engine.rules import get_rule
from ml.surrogate import generate as g
from ml.surrogate import schema

warnings.filterwarnings("ignore")
STREET = "rural_weak_63"


def test_splits_differ_by_month_adoption_and_held_out_combinations():
    fams = g.families(STREET)
    by = {s: [f for f in fams if f.split == s] for s in g.SPLITS}
    months = {s: {int(f.date[5:7]) for f in v} for s, v in by.items()}
    assert months["test"] == set(g.TEST_MONTHS) and not months["test"] & (months["train"] | months["tune"] | months["calibrate"])
    assert months["tune"].isdisjoint(months["calibrate"])
    dev = [f for f in fams if f.split != "test"]
    assert all((f.tap, f.mode) not in g.HELD_OUT for f in dev)
    assert {f.adoption for f in dev} == set(g.ADOPTION_DEV) and {f.adoption for f in by["test"]} == set(g.ADOPTION_TEST)
    assert {(f.tap, f.mode) for f in by["test"]} & g.HELD_OUT                 # the unseen combinations are tested
    assert len({f.id for f in fams}) == len(fams)
    assert [f.seed for f in g.families(STREET)] == [f.seed for f in fams]     # deterministic


def test_adoption_spreads_solar_evenly_along_the_street():
    net = compute.network(STREET)
    kwp = g.adoption_kwp(net, 0.5)
    assert (kwp > 0).sum() == round(0.5 * net.n_homes) and set(kwp[kwp > 0]) <= set(net.house_kwp)


@pytest.fixture(scope="module")
def family_run():
    net = compute.network(STREET)
    fam = next(f for f in g.families(STREET) if f.split == "train" and f.mode == "fixed_pf")
    return net, fam, g.run_family(net, fam, n_scenarios=1, boundary_share=0.25)


def test_family_states_are_valid_inputs_with_solver_labels(family_run):
    net, fam, out = family_run
    s = out["states"]
    base = ~out["boundary"]
    assert base.sum() == 96 and np.all(s.pv_kw <= s.pv_kwp + 1e-9)
    assert np.all(np.abs(s.battery_kw) <= g.BATTERY_KW) and (s.battery_kw != 0).any()
    assert np.all(s.tap_pos == fam.tap) and np.all(s.mode == schema.MODES.index(fam.mode))
    lab = out["labels"]
    assert lab.u_pu.shape == (len(s), len(net.lv_nodes), 3)
    assert np.isfinite(lab.u_pu[lab.converged]).all()


def test_boundary_states_sit_close_to_a_limit(family_run):
    _, _, out = family_run
    b = out["boundary"]
    assert b.any()
    ext = out["labels"].extremes()[b]
    kinds = out["boundary_kind"][b]
    for row, kind in zip(ext, kinds):
        name = g.BOUNDARY_KINDS[kind]
        if name == "loading":
            assert 95 <= max(row[2], row[3]) <= 105
        else:
            rule = get_rule(name.split("_", 1)[1])
            limit = rule.vmax_pu if name.startswith("vmax") else rule.vmin_pu
            value = row[0] if name.startswith("vmax") else row[1]
            assert abs(value - limit) * rule.nominal_v <= g.BOUNDARY_V + 1e-6


def test_battery_only_with_fixed_power_factor():
    net = compute.network(STREET)
    fam = next(f for f in g.families(STREET) if f.mode == "volt_var")
    out = g.run_family(net, fam, n_scenarios=1, boundary_share=0.0)
    assert np.all(out["states"].battery_kw == 0)


def test_out_of_range_kinds_leave_the_trained_box():
    net = compute.network(STREET)
    rng = np.random.default_rng(0)
    fam = next(f for f in g.families(STREET) if f.split == "test" and f.mode == "fixed_pf")
    base = g.run_family(net, fam, n_scenarios=1, boundary_share=0.0)["states"]
    ood = g.out_of_range(net, STREET, base, rng, per_kind=4)
    assert set(ood) == set(g.OOD_KINDS)
    up = ood["upstream_out"]["states"].upstream_pu
    assert np.all((up > g.UPSTREAM_LIMITS[1]) | (up < g.UPSTREAM_LIMITS[0]))
    assert np.all(np.isin(ood["tap_negative"]["states"].tap_pos, [-1, -2]))
    assert ood["phase_map"]["network"].house_phase.tolist() != net.house_phase.tolist()
    assert ood["layout"]["network"].line_to.tolist() != net.line_to.tolist()
    for kind, item in ood.items():
        assert len(item["states"]) == 4 and item["labels"].u_pu.shape[0] == 4, kind
