"""GridTwin API. Serves precomputed results instantly and computes other dates on demand.

Run:  uvicorn backend.main:app --reload
"""
import json
import sys
import warnings
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from engine import config  # noqa: E402
from engine.grid import build_grid, topology  # noqa: E402
from engine.ranking import evaluate_actions  # noqa: E402
from engine.scenarios import DEFAULT_DATE, SCENARIOS, run_scenario  # noqa: E402
from ml.early_warning import DEFAULT_FORECAST_DATE, early_warning  # noqa: E402

RESULTS_DIR = config.ROOT / "data" / "results"
FRONTEND_DIST = config.ROOT / "frontend" / "dist"

app = FastAPI(title="GridTwin API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _cached(name: str, compute):
    path = RESULTS_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    result = compute()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, separators=(",", ":")))
    return result


def _scenario(scenario: str) -> str:
    if scenario not in SCENARIOS:
        raise HTTPException(404, f"Unknown scenario {scenario}; choose from {list(SCENARIOS)}")
    return scenario


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/scenarios")
def scenarios():
    return [{"id": sid, **spec, "default_date": DEFAULT_DATE} for sid, spec in SCENARIOS.items()]


@app.get("/api/summary")
def summary(date: str = DEFAULT_DATE):
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
def run(scenario: str = "S4", date: str = DEFAULT_DATE):
    sid = _scenario(scenario)
    try:
        return _cached(f"run_{sid}_{date}", lambda: run_scenario(sid, date))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@app.get("/api/actions")
def actions(scenario: str = "S4", date: str = DEFAULT_DATE):
    sid = _scenario(scenario)
    try:
        return _cached(f"actions_{sid}_{date}", lambda: evaluate_actions(sid, date))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@lru_cache
def _forecast_table(target: str) -> pd.DataFrame:
    name = {"solar": "solar_forecast_2025.parquet", "demand": "demand_forecast_2019.parquet"}[target]
    return pd.read_parquet(config.PROCESSED_DIR / name)


@app.get("/api/forecast")
def forecast(target: str = Query("solar", pattern="^(solar|demand)$"), date: str = DEFAULT_FORECAST_DATE):
    table = _forecast_table(target)
    try:
        day = table.loc[date]
    except KeyError:
        raise HTTPException(404, f"No {target} forecast for {date}; range {table.index.min()} to {table.index.max()}")
    return {
        "target": target,
        "unit": "kW per installed kW" if target == "solar" else "kW per home",
        "date": date,
        "points": [{"t": t.strftime("%H:%M"), **{k: round(float(v), 4) for k, v in row.items()}}
                   for t, row in day.iterrows()],
    }


@app.get("/api/metrics")
def metrics():
    return json.loads((config.ROOT / "ml" / "reports" / "metrics.json").read_text())


@app.get("/api/early-warning")
def warning(date: str = DEFAULT_FORECAST_DATE):
    return _cached(f"early_warning_{date}", lambda: early_warning(date))


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
