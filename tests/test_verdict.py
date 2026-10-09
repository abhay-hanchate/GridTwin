from engine.verdict import binding_limit, build_verdict, describe


def _step(*items):
    return {"violations": [{"type": t, "element": "bus", "id": 1, "value": v, "limit": lim} for t, v, lim in items]}


def test_binding_limit_picks_the_most_frequent_type():
    steps = [_step(("overvoltage", 1.15, 1.10)), _step(("overvoltage", 1.12, 1.10)), _step(("trafo_overload", 120.0, 100))]
    b = binding_limit(steps)
    assert b["type"] == "overvoltage" and b["steps"] == 2 and b["worst"]["value"] == 1.15


def test_a_tie_prefers_the_transformer():
    steps = [_step(("overvoltage", 1.12, 1.10)), _step(("trafo_overload", 120.0, 100))]
    assert binding_limit(steps)["type"] == "trafo_overload"


def test_many_buses_in_one_step_count_once():
    steps = [_step(("overvoltage", 1.12, 1.10), ("overvoltage", 1.13, 1.10)), _step(("undervoltage", 0.85, 0.90))]
    b = binding_limit(steps)
    assert b["steps"] == 1 and b["type"] == "overvoltage" and b["worst"]["value"] == 1.13


def test_safe_day_has_no_binding_limit():
    assert binding_limit([{"violations": []}]) is None


def test_describe_uses_volts_and_percent():
    assert describe({"type": "overvoltage", "steps": 3, "worst": {"value": 1.1435, "limit": 1.10}}) == \
        "voltage reached 263 V against a 253 V limit in 3 steps"
    assert describe({"type": "undervoltage", "steps": 1, "worst": {"value": 0.85, "limit": 0.90}}) == \
        "voltage fell to 196 V against a 207 V limit in 1 step"
    assert describe({"type": "trafo_overload", "steps": 1, "worst": {"value": 172.0, "limit": 100}}) == \
        "transformer loading reached 172% against a 100% limit in 1 step"
    assert describe({"type": "solver_failure", "steps": 2, "worst": {"value": 0.0, "limit": 0.0}}) == \
        "the power flow did not converge in 2 steps"


def _result(action_id, label, steps, curtailed, limit=None):
    return {"action_id": action_id, "label": label, "remaining_violation_steps": steps,
            "cost": {"curtailed_kwh": curtailed}, "binding_limit": limit}


def test_verdict_with_a_safe_action():
    safe = [_result("a", "Fix A", 0, 0.0)]
    v = build_verdict(safe, safe)
    assert v["safe_action_found"] and v["recommended"] == "a" and v["binding_limit"] is None


def test_no_safe_action_names_the_binding_limit_and_the_closest_option():
    limit = {"type": "trafo_overload", "steps": 12, "worst": {"value": 172.0, "limit": 100}}
    results = [_result("a", "Fix A", 20, 0.0), _result("b", "Fix B", 12, 5.0, limit)]
    v = build_verdict(results, [])
    assert not v["safe_action_found"] and v["closest"] == "b" and v["recommended"] is None
    assert "transformer loading reached 172%" in v["message"] and "Fix B" in v["message"]
    assert v["binding_limit"] == limit
