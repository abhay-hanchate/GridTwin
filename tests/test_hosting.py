import warnings

import pytest

from engine.archetypes import build
from engine.dayinputs import scenarios_from_legacy
from engine.hosting import hosting_capacity
from engine.powerflow import day_inputs
from engine.rules import get_rule

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def street():
    net = build("benchmark_250")
    return net, scenarios_from_legacy(day_inputs("2019-05-15"), net)


def test_capacity_is_reproducible_ordered_and_reported_with_its_limit(street):
    a = hosting_capacity(*street, get_rule("pm10"), draws=8, seed=3)
    b = hosting_capacity(*street, get_rule("pm10"), draws=8, seed=3)
    assert a == b
    s = a["adoption_share"]
    assert 0 <= s["p10"] <= s["p50"] <= s["p90"] <= 1
    failed = list(a["share_of_draws_failed_by_level"].values())
    assert failed == sorted(failed) and failed[0] == 0                    # nobody fails at zero adoption
    assert a["binding"] in (None, "overvoltage", "undervoltage", "line_overload", "trafo_overload")


def test_a_tighter_rule_never_hosts_more(street):
    loose = hosting_capacity(*street, get_rule("pm10"), draws=8, seed=1)["adoption_share"]["p50"]
    tight = hosting_capacity(*street, get_rule("up_2005"), draws=8, seed=1)["adoption_share"]["p50"]
    assert tight <= loose


def test_zero_draws_is_an_error(street):
    with pytest.raises(ValueError, match="at least one"):
        hosting_capacity(*street, get_rule("pm10"), draws=0)
