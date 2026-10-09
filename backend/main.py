"""GridTwin API. Serves precomputed results instantly and computes other dates on demand.

Run:  uvicorn backend.main:app --reload
"""
import json
import os
import sys
import warnings
from datetime import date as Date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from engine import config  # noqa: E402
from engine.grid import build_grid, topology  # noqa: E402
from engine.hosting_capacity import estimate_hosting_capacity  # noqa: E402
from engine.ranking import evaluate_actions  # noqa: E402
from engine.rules import get_rule, load_rules  # noqa: E402
from engine.scenarios import DEFAULT_DATE, SCENARIOS, run_scenario  # noqa: E402
from engine.simulate import ACTIONS_BY_ID, simulate_fix  # noqa: E402
from ml.early_warning import DEFAULT_FORECAST_DATE, early_warning, forecast_sim, live_warning  # noqa: E402
from ml.live_forecast import (  # noqa: E402
    LiveForecastError,
    frame_from_result,
    live_solar_forecast,
    tomorrow_local,
)
from backend.cache import CorruptCacheError, load_or_compute  # noqa: E402
from backend.schemas import (  # noqa: E402
    EarlyWarningResponse,
    LiveForecastResponse,
    LiveWarningResponse,
    ModelReportResponse,
    ReadinessResponse,
)

RESULTS_DIR = config.ROOT / "data" / "results"
FRONTEND_DIST = config.ROOT / "frontend" / "dist"

app = FastAPI(title="GridTwin API", version="0.1.0")
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "GRIDTWIN_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET"], allow_headers=["*"])


def _cached(name: str, compute):
    try:
        return load_or_compute(RESULTS_DIR, name, compute)
    except CorruptCacheError as exc:
        raise HTTPException(503, str(exc)) from exc


def _scenario(scenario: str) -> str:
    if scenario not in SCENARIOS:
        raise HTTPException(404, f"Unknown scenario {scenario}; choose from {list(SCENARIOS)}")
    return scenario


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/readiness", response_model=ReadinessResponse)
def readiness():
    required = {
        "solar_forecast": config.PROCESSED_DIR / "solar_forecast_2025.parquet",
        "demand_forecast": config.PROCESSED_DIR / "demand_forecast_2019.parquet",
        "model_metrics": config.ROOT / "ml" / "reports" / "metrics.json",
        "solar_explainability": config.ROOT / "ml" / "reports" / "solar_feature_importance.json",
        "solar_model_manifest": config.ROOT / "ml" / "models" / "solar_manifest.json",
        "solar_model_p10": config.ROOT / "ml" / "models" / "solar_p10.txt",
        "solar_model_p50": config.ROOT / "ml" / "models" / "solar_p50.txt",
        "solar_model_p90": config.ROOT / "ml" / "models" / "solar_p90.txt",
    }
    files = {name: path.is_file() for name, path in required.items()}
    ready = all(files.values())
    return {"status": "ready" if ready else "degraded", "ready": ready, "files": files}


@app.get("/api/scenarios")
def scenarios():
    return [{"id": sid, **spec, "default_date": DEFAULT_DATE} for sid, spec in SCENARIOS.items()]


@app.get("/api/summary")
def summary(date: Date = Date.fromisoformat(DEFAULT_DATE)):
    """Headline numbers for every scenario, without the per-step detail (for the story view)."""
    out = []
    for sid, spec in SCENARIOS.items():
        r = run(sid, date)
        out.append({"id": sid, "name": spec["name"], "pv_share": spec["pv_share"], "band": spec["band"],
                    "limits": r["limits"], **r["summary"]})
    return out


@app.get("/api/grid")
def grid(scenario: str = "S4"):
    sid = _scenario(scenario)
    return _cached(f"grid_{sid}", lambda: topology(build_grid(SCENARIOS[sid]["pv_share"])))


@app.get("/api/run")
def run(scenario: str = "S4", date: Date = Date.fromisoformat(DEFAULT_DATE)):
    sid = _scenario(scenario)
    date_value = date.isoformat()
    try:
        return _cached(f"run_{sid}_{date_value}", lambda: run_scenario(sid, date_value))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@app.get("/api/actions")
def actions(scenario: str = "S4", date: Date = Date.fromisoformat(DEFAULT_DATE)):
    sid = _scenario(scenario)
    date_value = date.isoformat()
    try:
        return _cached(f"actions_{sid}_{date_value}", lambda: evaluate_actions(sid, date_value))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@app.get("/api/hosting-capacity")
def hosting_capacity(date: str = DEFAULT_DATE, band: str = "10"):
    """Estimate solar adoption the feeder can host, with and without the recommended fix."""
    try:
        get_rule(band)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return _cached(f"hosting_capacity_{date}_{band}", lambda: estimate_hosting_capacity(date, band))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@app.get("/api/rules")
def rules():
    """Every voltage rule the engine can check, with its source and how well it is verified."""
    return [r.as_dict() for r in load_rules().values()]


@lru_cache
def _forecast_table(target: str) -> pd.DataFrame:
    name = {"solar": "solar_forecast_2025.parquet", "demand": "demand_forecast_2019.parquet"}[target]
    return pd.read_parquet(config.PROCESSED_DIR / name)


@app.get("/api/forecast")
def forecast(
    target: Literal["solar", "demand"] = "solar",
    date: Date = Date.fromisoformat(DEFAULT_FORECAST_DATE),
):
    table = _forecast_table(target)
    date_value = date.isoformat()
    try:
        day = table.loc[date_value]
    except KeyError:
        raise HTTPException(404, f"No {target} forecast for {date}; range {table.index.min()} to {table.index.max()}")
    return {
        "target": target,
        "unit": "kW per installed kW" if target == "solar" else "kW per home",
        "date": date_value,
        "points": [{"t": t.strftime("%H:%M"), **{k: round(float(v), 4) for k, v in row.items()}}
                   for t, row in day.iterrows()],
    }


@app.get("/api/live-forecast", response_model=LiveForecastResponse)
def live_forecast(date: Date | None = None):
    """Fetch issue-time weather and run the frozen solar models for tomorrow (or `date`)."""
    target = date or tomorrow_local()
    try:
        return live_solar_forecast(target)
    except LiveForecastError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/live-early-warning", response_model=LiveWarningResponse)
def live_early_warning(
    date: Date | None = None,
    risk: Literal["p10", "p50", "p90"] = "p90",
    band: Literal["6", "10"] = "10",
):
    """Convert the live probabilistic solar forecast into feeder-voltage risk."""
    target = date or tomorrow_local()
    try:
        result = live_solar_forecast(target)
        return live_warning(target.isoformat(), frame_from_result(result), risk=risk, band=band)
    except LiveForecastError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, f"live warning inputs are unavailable: {exc}") from exc


@app.get("/api/metrics")
def metrics():
    path = config.ROOT / "ml" / "reports" / "metrics.json"
    if not path.is_file():
        raise HTTPException(503, "model metrics are unavailable; retrain the forecasts")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/model-report", response_model=ModelReportResponse)
def model_report(target: Literal["solar"] = "solar"):
    path = config.ROOT / "ml" / "reports" / f"{target}_feature_importance.json"
    if not path.is_file():
        raise HTTPException(503, f"{target} explainability report is unavailable")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/early-warning", response_model=EarlyWarningResponse)
def warning(
    date: Date = Date.fromisoformat(DEFAULT_FORECAST_DATE),
    risk: Literal["p10", "p50", "p90"] = "p90",
    band: Literal["6", "10"] = "10",
):
    date_value = date.isoformat()
    try:
        return _cached(
            f"early_warning_{date_value}_{risk}_band{band}",
            lambda: early_warning(date_value, risk=risk, band=band),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, f"warning inputs are unavailable: {exc}") from exc


@app.get("/api/fix-sim")
def fix_sim(
    scenario: str = "S4",
    action: str = "tap1_volt_var",
    date: Date = Date.fromisoformat(DEFAULT_DATE),
):
    """The same day without and with one fix, step by step, for the side-by-side simulator."""
    sid = _scenario(scenario)
    if action not in ACTIONS_BY_ID:
        raise HTTPException(404, f"Unknown fix {action}; choose from {list(ACTIONS_BY_ID)}")
    date_value = date.isoformat()
    return _cached(f"fixsim_{sid}_{action}_{date_value}", lambda: simulate_fix(sid, action, date_value))


@app.get("/api/forecast-sim")
def forecast_simulation(
    date: Date = Date.fromisoformat(DEFAULT_FORECAST_DATE),
    risk: Literal["p10", "p50", "p90"] = "p50",
    band: Literal["6", "10"] = "10",
):
    """The day-ahead solar case next to the ERA5/PVWatts reference simulation."""
    date_value = date.isoformat()
    try:
        return _cached(
            f"forecastsim_{date_value}_{risk}_band{band}",
            lambda: forecast_sim(date_value, risk=risk, band=band),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, f"forecast simulation inputs are unavailable: {exc}") from exc


@app.get("/api/insights")
def insights():
    """Real voltage quality measured by the CEEW smart meters in 2019."""
    return json.loads((config.PROCESSED_DIR / "voltage_stats.json").read_text())


# Serve the built dashboard from the same process when it exists.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        file = FRONTEND_DIST / path
        if path and file.is_file() and FRONTEND_DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
