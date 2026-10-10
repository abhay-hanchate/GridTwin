import pytest

from engine.explain import NUMBER, explain_risk, explain_verdict, rephrase, same_numbers, templates

RISK = {"level": "act", "first_act": "08:15", "first_watch": "07:45", "thresholds": {"watch": 0.2, "act": 0.5},
        "expected_unsafe_hours": {"mean": 8.57, "p10": 6.45, "p90": 10.75}, "peak_voltage_v": {"p50": 264.5},
        "calibration": {"reliable": False}}
FIXES_NO_SAFE = {"verdict": {"safe_action_found": False, "recommended": None, "closest": "tap2_volt_var",
                             "binding_limit": {"type": "undervoltage", "steps": 18, "worst": {"value": 0.904, "limit": 0.94}},
                             "still_needs": "about 8 V more voltage at the far end"},
                 "outcomes": [{"id": "tap2_volt_var", "label": "Tap +2 with IEEE 1547 Volt/VAR", "unsafe_steps": 25,
                               "cost": {"curtailed_kwh": 0, "operations": 0}}]}


def test_risk_text_uses_only_numbers_from_the_result():
    text = explain_risk(RISK, limit_v=253.0)
    assert "ACT" in text and "08:15" in text and "8.6 hours" in text and "264.5 V" in text and "253 V" in text
    allowed = {"08", "15", "8.6", "6.5", "10.8", "264.5", "253", "8", "10"}       # values plus "8 of 10 cases"
    assert set(NUMBER.findall(text)) <= allowed
    assert "not reliable as odds" in text
    calibrated = explain_risk({**RISK, "calibration": {"reliable": True, "applied": True}}, limit_v=253.0)
    assert "slightly better than the historical average" in calibrated and "not reliable" not in calibrated
    # a reliable map that was not applied (a fix, another street) leaves raw chances
    assert "not reliable as odds" in explain_risk({**RISK, "calibration": {"reliable": True, "applied": False}}, 253.0)


def test_calibrated_hours_have_no_scenario_range():
    risk = {**RISK, "expected_unsafe_hours": {"mean": 7.25, "p10": None, "p90": None},
            "calibration": {"reliable": True, "applied": True}}
    for lang in ("en", "hi"):
        text = explain_risk(risk, 253.0, lang)
        assert "7.2" in text and "None" not in text and "6.5" not in text


def test_no_safe_action_names_the_limit_and_what_is_still_needed():
    text = explain_verdict(FIXES_NO_SAFE)
    assert text.startswith("No safe action") and "25 unsafe" in text and "208 V" in text and "8 V more" in text


def test_hindi_has_the_same_numbers_and_is_marked_as_a_draft():
    en, hi = explain_risk(RISK, 253.0, "en"), explain_risk(RISK, 253.0, "hi")
    assert same_numbers(en.split(" These chances")[0], hi.split(" ये संभावनाएँ")[0])
    assert "review" in templates("hi")["_meta"]["review"]
    assert set(templates("hi")) == set(templates("en"))


def test_a_rephrase_that_changes_a_number_is_rejected(monkeypatch):
    monkeypatch.setenv("GRIDTWIN_LLM_REPHRASE", "1")
    original = "Expect about 8.6 hours of unsafe time."
    assert rephrase(original, lambda t: "Roughly 8.6 unsafe hours are expected.") == "Roughly 8.6 unsafe hours are expected."
    assert rephrase(original, lambda t: "Expect about 9 hours of unsafe time.") == original
    assert rephrase(original, lambda t: 1 / 0) == original
    monkeypatch.setenv("GRIDTWIN_LLM_REPHRASE", "0")
    assert rephrase(original, lambda t: "anything") == original


def test_unknown_language_lists_the_available_ones():
    with pytest.raises(KeyError, match="en"):
        templates("fr")
