"""control.replay: the closed loop keeps its state, labels every step honestly and replays deterministically."""
import pytest

from control.forecast import Perturbation
from control.replay import ReplayConfig, run
from control.types import Status

CFG = ReplayConfig(run_id="test", start=44, end=52, n_scenarios=20,
                   perturbations=(Perturbation("pv_scale", 46, 52, 0.5, "cloud"),))


@pytest.fixture(scope="module")
def replay():
    return run(CFG)


def test_energy_carries_over_and_never_leaves_its_limits(replay):
    recs = replay.records
    bat = CFG.battery()
    assert recs[0].energy_before_kwh == pytest.approx(CFG.soc_start * CFG.battery_kwh)
    for a, b in zip(recs, recs[1:]):
        assert b.energy_before_kwh == pytest.approx(a.energy_after_kwh)               # persistent state
    for r in recs:
        assert bat.e_min - 1e-6 <= r.energy_after_kwh <= bat.e_max + 1e-6
        assert r.energy_after_kwh == pytest.approx(bat.next_energy(r.energy_before_kwh, r.action["battery_kw"]), abs=1e-3)
        assert abs(r.action["battery_kw"]) <= CFG.battery_kw + 1e-9
        assert all(0 <= x <= 1 for x in r.action["keep"])
        assert r.planner["horizon"] >= 8


def test_only_physically_checked_safe_steps_are_called_safe(replay):
    for r in replay.records:
        assert r.status in {s.value for s in Status}
        if r.status == Status.VERIFIED_SAFE.value:
            assert r.after["safe"] is True
        else:
            assert r.after["safe"] is False and r.reason


def test_the_cloud_shows_up_as_a_residual_and_a_replan_trigger(replay):
    late = [r for r in replay.records if r.step >= 48]
    assert any(r.forecast["residual"]["pv"] < -0.15 for r in late)
    assert any(any("solar residual" in t for t in r.replan_triggers) for r in late)
    assert replay.provenance["observations"].startswith("simulated_observation")


def test_the_reactive_rule_ran_on_the_same_observations(replay):
    assert len(replay.baseline["safe"]) == len(replay.records)
    assert replay.baseline["energy_kwh"][0] == pytest.approx(CFG.soc_start * CFG.battery_kwh)
    assert replay.summary["baseline_unsafe_steps"] == sum(not s for s in replay.baseline["safe"])


def test_a_replay_is_deterministic():
    short = ReplayConfig(run_id="det", start=48, end=50, n_scenarios=20)
    a, b = run(short), run(short)
    assert [r.action for r in a.records] == [r.action for r in b.records]
    assert [r.energy_after_kwh for r in a.records] == [r.energy_after_kwh for r in b.records]
