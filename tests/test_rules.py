import pytest

from engine.rules import get_rule, load_rules


def test_aliases_keep_old_band_ids_working():
    assert get_rule("10").id == "pm10"
    assert get_rule("6").id == "up_2005"


def test_up_supply_code_is_plus_minus_six_percent_with_source():
    rule = get_rule("up_2005")
    assert (rule.vmin_pu, rule.vmax_pu) == (0.94, 1.06)
    assert (rule.vmin_v, rule.vmax_v) == (216.2, 243.8)
    assert rule.region == "Uttar Pradesh"
    assert "UPERC" in rule.source and "CEEW" in rule.source
    assert rule.verification == "secondary"


def test_default_band_is_marked_unverified():
    assert get_rule("pm10").verification == "unverified"


def test_asymmetric_rules_are_supported():
    rule = get_rule("plus6_minus10")
    assert (rule.vmin_pu, rule.vmax_pu) == (0.90, 1.06)
    assert rule.vmin_v == 207.0 and rule.vmax_v == 243.8


def test_unknown_rule_lists_valid_ids():
    with pytest.raises(KeyError) as err:
        get_rule("nope")
    assert "pm10" in str(err.value) and "up_2005" in str(err.value)


def test_every_rule_is_well_formed():
    for rule in load_rules().values():
        assert 0.5 < rule.vmin_pu < 1.0 < rule.vmax_pu < 1.5
        assert rule.source.strip()
        assert rule.verification in {"primary", "secondary", "unverified"}
        assert set(rule.as_dict()) >= {"id", "label", "vmin_v", "vmax_v", "source", "verification"}
