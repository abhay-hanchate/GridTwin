"""Generate an auditable feature-importance report for the solar P50 model.

The report deliberately combines LightGBM split-gain importance with permutation
importance on the untouched 2025 test period. Neither measure is causal.

Usage: python -m ml.explain
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.forecast import MODEL_DIR, RANDOM_SEED, solar_training_data

REPORT_DIR = Path(__file__).resolve().parent / "reports"
JSON_REPORT = REPORT_DIR / "solar_feature_importance.json"
CSV_REPORT = REPORT_DIR / "solar_feature_importance.csv"

FEATURE_DEFINITIONS = {
    "fc_pv": "PVWatts output calculated from the genuine previous-day weather forecast",
    "fc_ghi": "previous-day forecast global horizontal irradiance",
    "fc_cloud": "previous-day forecast cloud cover",
    "fc_temp": "previous-day forecast air temperature",
    "clearsky_ghi": "deterministic clear-sky irradiance for location and time",
    "hour": "local hour of day",
    "doy": "day of year",
}


def normalize_gain(gain: np.ndarray) -> np.ndarray:
    gain = np.asarray(gain, dtype=float)
    total = float(gain.sum())
    return gain / total if total > 0 else np.zeros_like(gain)


def permutation_mae_increase(
    predict: Callable[[pd.DataFrame], np.ndarray],
    X: pd.DataFrame,
    y: pd.Series,
    repeats: int = 5,
    seed: int = RANDOM_SEED,
) -> dict[str, float]:
    """Return mean test-MAE increase when each feature is independently shuffled."""
    baseline = float(np.mean(np.abs(np.asarray(predict(X)) - y.to_numpy())))
    rng = np.random.default_rng(seed)
    scores: dict[str, float] = {}
    for column in X.columns:
        increases = []
        for _ in range(repeats):
            shuffled = X.copy()
            shuffled[column] = rng.permutation(shuffled[column].to_numpy())
            mae = float(np.mean(np.abs(np.asarray(predict(shuffled)) - y.to_numpy())))
            increases.append(mae - baseline)
        scores[column] = float(np.mean(increases))
    return scores


def build_solar_report() -> dict:
    model_path = MODEL_DIR / "solar_p50.txt"
    if not model_path.exists():
        raise FileNotFoundError("solar_p50 model is missing; run `python -m ml.forecast` first")

    X, y, masks = solar_training_data()
    test_X, test_y = X.loc[masks["test"]], y.loc[masks["test"]]
    booster = lgb.Booster(model_file=str(model_path))
    gain = normalize_gain(booster.feature_importance(importance_type="gain"))
    permutation = permutation_mae_increase(booster.predict, test_X, test_y)

    importance = [
        {
            "feature": name,
            "definition": FEATURE_DEFINITIONS[name],
            "gain_normalized": round(float(value), 6),
            "permutation_mae_increase": round(float(permutation[name]), 6),
        }
        for name, value in sorted(zip(X.columns, gain), key=lambda item: item[1], reverse=True)
    ]
    return {
        "model": "solar_p50",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_period": "2025 daylight hours (untouched temporal test set)",
        "features_available_at_issue_time": True,
        "importance": importance,
        "limitations": [
            "Importance describes predictive contribution, not causality.",
            "The target is ERA5/PVWatts-derived solar output, not measured panel production.",
            "Correlated irradiance features can share or exchange importance.",
        ],
    }


def main() -> None:
    report = build_solar_report()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(report["importance"]).to_csv(CSV_REPORT, index=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
