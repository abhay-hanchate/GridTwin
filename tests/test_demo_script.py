import json

from scripts import demo_script


def _risk(level, first, mean, reliable):
    p = [0.1] * 96
    p[36] = 0.9                                           # 09:00 is the riskiest quarter hour
    return {"level": level, "first_act": first, "expected_unsafe_hours": {"mean": mean, "p10": mean - 2, "p90": mean + 2},
            "calibration": {"reliable": reliable}, "p_unsafe": p,
            "t": [f"{i // 4:02d}:{i % 4 * 15:02d}" for i in range(96)]}


def test_script_reads_every_number_from_the_results(tmp_path, monkeypatch):
    v2 = tmp_path / "data" / "results" / "v2"
    v2.mkdir(parents=True)
    files = {
        ("risk", "sunny", "up_2005"): _risk("act", "06:00", 16.7, False),
        ("risk", "sunny", "pm10"): _risk("act", "06:15", 9.0, True),
        ("risk", "cloudy", "pm10"): _risk("ok", None, 0.5, True),
        ("fixes", "sunny", "pm10"): {"verdict": {"safe_action_found": True, "recommended": "t1"},
                                     "outcomes": [{"id": "t1", "label": "Tap +1 with IEEE 1547 Volt/VAR"}]},
        ("fixes", "sunny", "up_2005"): {"verdict": {"safe_action_found": False, "still_needs": "a heavier conductor",
                                                    "message": "No safe action: every option leaves violations. Closest is X."},
                                        "outcomes": []},
    }
    entries = []
    for i, ((route, day, rule), body) in enumerate(files.items()):
        (v2 / f"k{i}.json").write_text(json.dumps(body))
        entries.append({"route": route, "day_type": day, "rule": rule, "key": f"k{i}"})
    (v2 / "index.json").write_text(json.dumps({"code_version": "abc", "entries": entries,
                                               "demo_dates": {"sunny": "2025-05-15", "cloudy": "2025-08-05", "mixed": "2025-11-19"}}))
    gates = [{"gate": "G1", "status": "pass", "measured": {"max_voltage_diff_v": 0.001, "speedup": 813.1}},
             {"gate": "G8", "status": "fail", "measured": {"pm10": {"brier_skill_calibrated": 0.023},
                                                          "up_2005": {"brier_skill_calibrated": -5.46}}}]
    (tmp_path / "data" / "results" / "results.json").write_text(json.dumps({"gates": gates}))
    monkeypatch.setattr(demo_script, "ROOT", tmp_path)
    monkeypatch.setattr(demo_script, "V2", v2)
    text = demo_script.build()
    assert "Tap +1 with IEEE 1547 Volt/VAR" in text and "**No safe action**" in text and "heavier conductor" in text
    assert "about 16.7 hours" in text and "0.001 V" in text and "813.1 times" in text and "-5.46" in text
    assert "switch the rule picker to +/-10%" in text and "click a point at the far end" in text and "POST" not in text
    assert "Home tab" not in text and "sunny demo day" not in text and "**Tomorrow**" in text and "**Try a change**" in text
    assert "G8 fail" in text and "not reliable as odds" in text
    assert "2025-05-15" in text                                               # the day to pick in offline mode
    assert "around **09:00** (90%), against 10% at 12:00" in text            # computed from the curve, not asserted


def test_calibrated_hours_have_no_range_and_say_so():
    risk = {"expected_unsafe_hours": {"mean": 7.28, "p10": None, "p90": None},
            "calibration": {"reliable": True, "applied": True}}
    assert demo_script._hours(risk) == "about 7.3 hours"
    assert demo_script._chances(risk).startswith("recalibrated")
    assert demo_script._chances({"calibration": {"reliable": True, "applied": False}}).startswith("raw")


def test_numbers_round_like_the_dashboard():
    # Checked with Node: (20.25).toFixed(1) "20.3", (15).toFixed(1) "15.0" (one() drops ".0"), (1.05).toFixed(1) "1.1",
    # (0.15).toFixed(1) "0.1" (the float is 0.1499...), Math.round(0.125 * 100) 13, Math.round(0.985 * 100) 99.
    one, pct = demo_script.one, demo_script.pct
    assert one(20.25) == "20.3" and round(20.25, 1) == 20.2              # Python's round would say a number not on screen
    assert one(15.0) == "15" and one(16.7) == "16.7" and one(1.05) == "1.1" and one(0.15) == "0.1"
    assert pct(0.125) == "13%" and pct(0.985) == "99%" and pct(0.0) == "0%"
