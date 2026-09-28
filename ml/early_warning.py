"""Early warning: run tomorrow's solar forecast through the grid to predict unsafe voltage.

The forecast day is in 2025 (the test year of the solar model). Household demand and upstream
voltage come from the same calendar day of 2019, the latest year with CEEW smart-meter data;
this is labelled as a proxy.
"""
import pandas as pd

from engine import config
from engine.grid import build_grid
from engine.powerflow import DayInputs, day_inputs, run_day

DEFAULT_FORECAST_DATE = "2025-05-15"


def solar_forecast(date: str) -> pd.DataFrame:
    fc = pd.read_parquet(config.PROCESSED_DIR / "solar_forecast_2025.parquet")
    return fc.loc[date]


def early_warning(date: str = DEFAULT_FORECAST_DATE, pv_share: float = 1.0, band: str = "10") -> dict:
    fc = solar_forecast(date)
    proxy_day = f"2019-{date[5:]}"
    base = day_inputs(proxy_day)

    out = {"date": date, "demand_proxy_date": proxy_day, "pv_share": pv_share, "band": band, "cases": {}}
    for case in ["p50", "p90", "actual"]:
        pv = pd.Series(fc[case].to_numpy(), index=base.load_kw.index)
        inputs = DayInputs(date, base.load_kw, pv, base.upstream_vm_pu)
        run = run_day(build_grid(pv_share), inputs, band=band, detail=False)
        unsafe = [s["t"][-5:] for s in run["steps"] if s["violations"]]
        out["cases"][case] = {
            "violation_steps": run["summary"]["violation_steps"],
            "max_vm_pu": run["summary"]["max_vm_pu"],
            "first_unsafe": unsafe[0] if unsafe else None,
            "unsafe_times": unsafe,
        }
    out["provenance"] = {
        "solar": "forecast: LightGBM on day-ahead weather forecast; actual: pvlib on ERA5",
        "demand": f"proxy: CEEW Mathura smart meters on {proxy_day}",
    }
    return out
