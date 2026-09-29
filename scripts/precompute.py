"""Precompute every result the dashboard needs into data/results (about 8 minutes).

Usage:  python scripts/precompute.py
"""
import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from engine import config  # noqa: E402
from engine.grid import build_grid, topology  # noqa: E402
from engine.hosting_capacity import estimate_hosting_capacity  # noqa: E402
from engine.ranking import evaluate_actions  # noqa: E402
from engine.scenarios import DEFAULT_DATE, SCENARIOS, run_scenario  # noqa: E402
from engine.actions import ACTIONS  # noqa: E402
from engine.simulate import simulate_fix  # noqa: E402
from ml.early_warning import DEFAULT_FORECAST_DATE, early_warning, forecast_sim  # noqa: E402

RESULTS_DIR = config.ROOT / "data" / "results"


def save(name: str, payload: dict) -> None:
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(payload, separators=(",", ":")))
    print(f"saved {name}", flush=True)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    for sid, spec in SCENARIOS.items():
        save(f"grid_{sid}", topology(build_grid(spec["pv_share"])))
        save(f"run_{sid}_{DEFAULT_DATE}", run_scenario(sid, DEFAULT_DATE))
        save(f"actions_{sid}_{DEFAULT_DATE}", evaluate_actions(sid, DEFAULT_DATE))
    save(f"hosting_capacity_{DEFAULT_DATE}_10", estimate_hosting_capacity(DEFAULT_DATE, "10"))
    save(f"early_warning_{DEFAULT_FORECAST_DATE}", early_warning(DEFAULT_FORECAST_DATE))
    save(f"forecastsim_{DEFAULT_FORECAST_DATE}", forecast_sim(DEFAULT_FORECAST_DATE))
    # Side-by-side fix simulations for the headline scenario; other scenarios compute on demand.
    for action in ACTIONS:
        save(f"fixsim_S4_{action.id}_{DEFAULT_DATE}", simulate_fix("S4", action.id, DEFAULT_DATE))
    print(f"done in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
