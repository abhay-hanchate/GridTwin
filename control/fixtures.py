"""The declared demonstration runs of Addition 1. Configured before their results were seen and never tuned after;
the forecast correction settings come from a development day (docs/DECISIONS.md)."""
from __future__ import annotations

from control.forecast import Perturbation as P
from control.replay import ReplayConfig

CLOUD = (P("pv_scale", 46, 54, 0.5, "unforecast cloud: half the sun from 11:30 to 13:30"),)

FIXTURES: dict[str, ReplayConfig] = {
    "forecast_error": ReplayConfig(
        run_id="forecast_error", title="Forecast error: a cloud the forecast did not see",
        start=36, end=72, perturbations=CLOUD),
    "battery_only": ReplayConfig(
        run_id="battery_only", title="Battery only, against the reactive rule (same observations as forecast_error)",
        start=36, end=72, curtail=False, perturbations=CLOUD),
    "battery_saturation": ReplayConfig(
        run_id="battery_saturation", title="Battery saturation: a nearly full battery before the solar peak",
        start=36, end=60, soc_start=0.85),
    "depletion_infeasible": ReplayConfig(
        run_id="depletion_infeasible",
        title="Battery depletion and an infeasible evening on the weak street, with permitted switching",
        network_id="rural_weak_63", start=64, end=88, soc_start=0.4, switching=True,
        perturbations=(P("upstream_shift", 72, 86, -0.10, "grid voltage sag of 0.10 pu from 18:00 to 21:30"),
                       P("load_scale", 72, 88, 1.5, "evening demand 50% above the forecast from 18:00"))),
}
