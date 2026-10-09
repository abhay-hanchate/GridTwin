"""Name the limit that stops a fix from working, and build the honest verdict.

The binding limit of a day is the violation type present in the most 15-minute steps (each type counted once per
step); its evidence is the instance furthest beyond its limit. Ties go to the asset that is hardest to fix:
transformer, then wire, then voltage, then a solver failure.
"""
from __future__ import annotations

NOMINAL_V = 230.0
ORDER = ("trafo_overload", "line_overload", "overvoltage", "undervoltage", "solver_failure")


def binding_limit(steps: list[dict]) -> dict | None:
    counts: dict[str, int] = {}
    worst: dict[str, dict] = {}
    for s in steps:
        for t in {v["type"] for v in s["violations"]}:
            counts[t] = counts.get(t, 0) + 1
        for v in s["violations"]:
            cur = worst.get(v["type"])
            if cur is None or abs(v["value"] - v["limit"]) > abs(cur["value"] - cur["limit"]):
                worst[v["type"]] = v
    if not counts:
        return None

    def rank(t: str) -> int:
        return ORDER.index(t) if t in ORDER else len(ORDER)
    top = min(counts, key=lambda t: (-counts[t], rank(t)))
    return {"type": top, "steps": counts[top], "worst": worst[top]}


def describe(limit: dict) -> str:
    t, n, w = limit["type"], limit["steps"], limit["worst"]
    when = f"in {n} step{'s' if n != 1 else ''}"
    if t == "overvoltage":
        return f"voltage reached {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "undervoltage":
        return f"voltage fell to {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "trafo_overload":
        return f"transformer loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    if t == "line_overload":
        return f"wire loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    return f"the power flow did not converge {when}"


def build_verdict(results: list[dict], safe: list[dict]) -> dict:
    """`results` are all evaluated options, `safe` the acceptable ones already ranked best first."""
    if safe:
        return {"safe_action_found": True, "recommended": safe[0]["action_id"],
                "message": f"Recommended: {safe[0]['label']}", "binding_limit": None, "closest": None}
    closest = min(results, key=lambda r: (r["remaining_violation_steps"], r["cost"]["curtailed_kwh"]))
    limit = closest.get("binding_limit")
    why = f" The limit that stops it: {describe(limit)}." if limit else ""
    return {"safe_action_found": False, "recommended": None, "closest": closest["action_id"], "binding_limit": limit,
            "message": (f"No safe action: every option leaves violations. Closest is '{closest['label']}' with "
                        f"{closest['remaining_violation_steps']} unsafe steps.{why}")}
