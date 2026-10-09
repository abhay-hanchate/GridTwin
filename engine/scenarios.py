"""The test scenarios and a single entry point to run one."""
from engine.grid import build_grid
from engine.powerflow import day_inputs, run_day

DEFAULT_DATE = "2019-05-15"

SCENARIOS = {
    "S1": {"name": "No rooftop solar (today)", "pv_share": 0.0, "band": "10"},
    "S2": {"name": "30% of homes with 3 kW solar", "pv_share": 0.3, "band": "10"},
    "S3": {"name": "60% of homes with 3 kW solar", "pv_share": 0.6, "band": "10"},
    "S4": {"name": "Every home with 3 kW solar", "pv_share": 1.0, "band": "10"},
    "S5": {"name": "Every home with solar, UP Supply Code rule (+/-6%)", "pv_share": 1.0, "band": "up_2005"},
}


def run_scenario(scenario_id: str, date: str = DEFAULT_DATE, detail: bool = True) -> dict:
    spec = SCENARIOS[scenario_id]
    inputs = day_inputs(date)
    result = run_day(build_grid(spec["pv_share"]), inputs, band=spec["band"], detail=detail)
    baseline = run_day(build_grid(0.0), inputs, band=spec["band"], detail=False)
    result["summary"]["violation_steps_without_solar"] = baseline["summary"]["violation_steps"]
    result["summary"]["violation_steps_from_solar"] = (
        result["summary"]["violation_steps"] - baseline["summary"]["violation_steps"]
    )
    return {"scenario_id": scenario_id, "name": spec["name"], "pv_share": spec["pv_share"],
            "band": spec["band"], **result}
