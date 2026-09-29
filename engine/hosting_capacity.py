"""Estimate rooftop-solar hosting capacity by replaying a day across PV penetrations."""
from engine import config
from engine.grid import build_grid
from engine.powerflow import day_inputs, run_day
from engine.scenarios import DEFAULT_DATE
from engine.simulate import ACTIONS_BY_ID, worst_bus

PENETRATION_STEPS = 10
RECOMMENDED_ACTION_ID = "tap1_volt_var"


def _capacity_summary(point: dict, unsafe_steps: int, found_safe_level: bool = True) -> dict:
    return {
        "pv_share": point["pv_share"],
        "solar_homes": point["solar_homes"],
        "installed_kw": point["installed_kw"],
        "unsafe_steps": unsafe_steps,
        "found_safe_level": found_safe_level,
    }


def estimate_hosting_capacity(date: str = DEFAULT_DATE, band: str = "10") -> dict:
    """Sweep 0–100% rooftop adoption in 10% increments, with and without the best fix.

    Without a fix, existing unsafe periods are treated as the baseline: capacity means
    solar adds no further unsafe 15-minute steps. With the recommended fix, capacity
    means all 96 steps are safe.
    """
    inputs = day_inputs(date)
    action = ACTIONS_BY_ID[RECOMMENDED_ACTION_ID]
    total_homes = len(build_grid(0.0).load)
    points = []

    for step in range(PENETRATION_STEPS + 1):
        requested_share = step / PENETRATION_STEPS
        solar_homes = round(requested_share * total_homes)
        share = solar_homes / total_homes

        base = run_day(build_grid(share), inputs, band=band, detail=True)
        net = build_grid(share)
        hook = action.make_hook(net, worst_bus(base), base["limits"]["vm_max_pu"])
        fixed = run_day(net, inputs, band=band, hook=hook, detail=False)

        points.append({
            "pv_share": round(share, 4),
            "solar_homes": solar_homes,
            "installed_kw": round(solar_homes * config.PV_KWP_PER_HOME, 1),
            "unsafe_steps_without_fix": base["summary"]["violation_steps"],
            "unsafe_steps_with_fix": fixed["summary"]["violation_steps"],
            "solver_failed_steps_without_fix": base["summary"]["solver_failed_steps"],
            "solver_failed_steps_with_fix": fixed["summary"]["solver_failed_steps"],
            "max_voltage_without_fix": round(base["summary"]["max_vm_pu"] * config.NOMINAL_VOLTAGE_V, 1),
            "max_voltage_with_fix": round(fixed["summary"]["max_vm_pu"] * config.NOMINAL_VOLTAGE_V, 1),
        })

    baseline_unsafe = points[0]["unsafe_steps_without_fix"]
    for point in points:
        point["safe_without_fix"] = (
            point["unsafe_steps_without_fix"] <= baseline_unsafe
            and point["solver_failed_steps_without_fix"] == 0
        )
        point["safe_with_fix"] = (
            point["unsafe_steps_with_fix"] == 0
            and point["solver_failed_steps_with_fix"] == 0
        )

    without_fix = max((p for p in points if p["safe_without_fix"]), key=lambda p: p["pv_share"])
    safe_with_fix = [p for p in points if p["safe_with_fix"]]
    with_fix = max(safe_with_fix, key=lambda p: p["pv_share"]) if safe_with_fix else points[0]
    return {
        "date": date,
        "band": band,
        "total_homes": total_homes,
        "kw_per_solar_home": config.PV_KWP_PER_HOME,
        "resolution_percent": 100 // PENETRATION_STEPS,
        "baseline_unsafe_steps": baseline_unsafe,
        "recommended_action": RECOMMENDED_ACTION_ID,
        "criteria": {
            "without_fix": "No more unsafe 15-minute steps than the no-solar baseline.",
            "with_fix": "Zero unsafe 15-minute steps after the recommended action.",
        },
        "capacity": {
            "without_fix": _capacity_summary(without_fix, without_fix["unsafe_steps_without_fix"]),
            "with_fix": _capacity_summary(
                with_fix, with_fix["unsafe_steps_with_fix"], found_safe_level=bool(safe_with_fix)
            ),
        },
        "points": points,
    }
