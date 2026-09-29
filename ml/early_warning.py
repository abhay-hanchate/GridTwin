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
RISK_CASES = ("p10", "p50", "p90")


def solar_forecast(date: str) -> pd.DataFrame:
    fc = pd.read_parquet(config.PROCESSED_DIR / "solar_forecast_2025.parquet")
    return fc.loc[date]


def forecast_sim(
    date: str = DEFAULT_FORECAST_DATE,
    pv_share: float = 1.0,
    band: str = "10",
    risk: str = "p50",
) -> dict:
    """Compare a day-ahead solar case with the ERA5/PVWatts reference simulation."""
    from engine.grid import lv_buses
    from engine.simulate import compact

    if risk not in RISK_CASES:
        raise ValueError(f"risk must be one of {RISK_CASES}")
    fc = solar_forecast(date)
    base = day_inputs(f"2019-{date[5:]}")
    runs, bus_ids = {}, None
    for case in [risk, "actual"]:
        pv = pd.Series(fc[case].to_numpy(), index=base.load_kw.index)
        net = build_grid(pv_share)
        bus_ids = bus_ids or [int(b) for b in lv_buses(net)]
        runs[case] = run_day(net, DayInputs(date, base.load_kw, pv, base.upstream_vm_pu), band=band, detail=True)
    return {
        "date": date, "band": band, "risk_band": risk, "limits": runs[risk]["limits"],
        "times": [s["t"][-5:] for s in runs[risk]["steps"]],
        "bus_ids": bus_ids,
        "before": compact(runs[risk], bus_ids),
        "after": compact(runs["actual"], bus_ids),
        "solar_kw_per_kwp": {c: [round(float(v), 4) for v in fc[c]] for c in ["p10", "p50", "p90", "actual"]},
        "provenance": {
            "prediction": "LightGBM using a weather forecast issued the previous day",
            "reference": "ERA5 reanalysis converted to PV output with pvlib; not measured panel output",
            "demand_and_voltage": f"CEEW Mathura historical proxy from 2019-{date[5:]}",
        },
    }


def early_warning(
    date: str = DEFAULT_FORECAST_DATE,
    pv_share: float = 1.0,
    band: str = "10",
    risk: str = "p90",
) -> dict:
    if risk not in RISK_CASES:
        raise ValueError(f"risk must be one of {RISK_CASES}")
    fc = solar_forecast(date)
    proxy_day = f"2019-{date[5:]}"
    base = day_inputs(proxy_day)

    out = {
        "date": date,
        "risk_band": risk,
        "demand_mode": "historical_proxy",
        "demand_proxy_date": proxy_day,
        "pv_share": pv_share,
        "band": band,
        "cases": {},
    }
    for case in [*RISK_CASES, "actual"]:
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
    out["predicted"] = out["cases"][risk]
    out["reference"] = out["cases"]["actual"]
    out["provenance"] = {
        "solar_prediction": "LightGBM using a weather forecast issued the previous day",
        "solar_reference": "ERA5 reanalysis converted with pvlib; a proxy, not measured panel production",
        "demand": f"CEEW Mathura historical proxy from {proxy_day}; the demand ML demo does not drive this warning",
        "upstream_voltage": f"CEEW Mathura historical proxy from {proxy_day}",
        "grid": "SimBench benchmark adapted with Indian overhead-line assumptions",
    }
    return out


def live_warning(
    date: str,
    forecast: pd.DataFrame,
    pv_share: float = 1.0,
    band: str = "10",
    risk: str = "p90",
) -> dict:
    """Run a live probabilistic forecast without pretending tomorrow's actual is known."""
    if risk not in RISK_CASES:
        raise ValueError(f"risk must be one of {RISK_CASES}")
    missing = set(RISK_CASES) - set(forecast.columns)
    if missing or len(forecast) != 96:
        raise ValueError(f"live forecast needs 96 P10/P50/P90 rows; missing {sorted(missing)}")
    proxy_day = f"2019-{date[5:]}"
    base = day_inputs(proxy_day)
    out = {
        "date": date,
        "risk_band": risk,
        "demand_mode": "historical_proxy",
        "demand_proxy_date": proxy_day,
        "pv_share": pv_share,
        "band": band,
        "cases": {},
    }
    for case in RISK_CASES:
        pv = pd.Series(forecast[case].to_numpy(), index=base.load_kw.index)
        run = run_day(
            build_grid(pv_share),
            DayInputs(date, base.load_kw, pv, base.upstream_vm_pu),
            band=band,
            detail=False,
        )
        unsafe = [step["t"][-5:] for step in run["steps"] if step["violations"]]
        out["cases"][case] = {
            "violation_steps": run["summary"]["violation_steps"],
            "max_vm_pu": run["summary"]["max_vm_pu"],
            "first_unsafe": unsafe[0] if unsafe else None,
            "unsafe_times": unsafe,
        }
    out["predicted"] = out["cases"][risk]
    out["provenance"] = {
        "solar_prediction": "live Open-Meteo weather processed by frozen GridTwin LightGBM quantile models",
        "demand": f"CEEW Mathura historical proxy from {proxy_day}; not a live demand forecast",
        "upstream_voltage": f"CEEW Mathura historical proxy from {proxy_day}",
        "grid": "SimBench benchmark adapted with Indian overhead-line assumptions",
        "reference": "unavailable until the target day has occurred",
    }
    return out
