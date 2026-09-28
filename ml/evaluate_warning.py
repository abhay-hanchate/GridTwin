"""Evaluate GridTwin early warnings across eligible days and select a cloudy challenge day.

The challenge day is selected only from quantities available in the day-ahead solar
forecast. This avoids cherry-picking a date after looking at the reference outcome.

Usage: python -m ml.evaluate_warning [--stride 1] [--max-days N] [--risk p50]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine import config
from engine.powerflow import day_inputs
from ml.early_warning import RISK_CASES, early_warning

REPORT_PATH = Path(__file__).resolve().parent / "reports" / "early_warning_evaluation.json"
RESULTS_DIR = config.ROOT / "data" / "results"


def forecast_challenge_score(day: pd.DataFrame) -> float:
    """Forecast-only cloud/variability score used before reference outcomes are inspected."""
    daylight = day[day["p90"] > 0.01]
    if daylight.empty:
        return 0.0
    uncertainty = float((daylight["p90"] - daylight["p10"]).mean())
    variability = float(daylight["p50"].diff().abs().sum() / max(daylight["p50"].sum(), 1e-9))
    return uncertainty + variability


def eligible_dates(start: str = "2025-05-01", end: str = "2025-12-31") -> list[dict]:
    forecasts = pd.read_parquet(config.PROCESSED_DIR / "solar_forecast_2025.parquet").loc[start:end]
    candidates = []
    for timestamp, day in forecasts.groupby(forecasts.index.normalize()):
        if len(day) != 96 or day[["p10", "p50", "p90", "actual"]].isna().any().any():
            continue
        date = timestamp.strftime("%Y-%m-%d")
        try:
            base = day_inputs(f"2019-{date[5:]}")
        except (KeyError, ValueError):
            continue
        if len(base.load_kw) != 96 or len(base.upstream_vm_pu) != 96:
            continue
        candidates.append({"date": date, "challenge_score": forecast_challenge_score(day)})
    return candidates


def _minutes(value: str | None) -> int | None:
    if value is None:
        return None
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def summarise(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("at least one evaluated day is required")
    duration_errors = [abs(r["predicted_steps"] - r["reference_steps"]) * 15 for r in rows]
    peak_errors = [abs(r["predicted_peak_pu"] - r["reference_peak_pu"]) * 230 for r in rows]
    start_errors = []
    for row in rows:
        predicted, reference = _minutes(row["predicted_start"]), _minutes(row["reference_start"])
        if predicted is not None and reference is not None:
            start_errors.append(abs(predicted - reference))
    tp = sum(r["predicted_steps"] > 0 and r["reference_steps"] > 0 for r in rows)
    fp = sum(r["predicted_steps"] > 0 and r["reference_steps"] == 0 for r in rows)
    fn = sum(r["predicted_steps"] == 0 and r["reference_steps"] > 0 for r in rows)
    return {
        "days": len(rows),
        "unsafe_duration_mae_minutes": round(float(np.mean(duration_errors)), 2),
        "unsafe_duration_median_error_minutes": round(float(np.median(duration_errors)), 2),
        "peak_voltage_mae_v": round(float(np.mean(peak_errors)), 3),
        "first_warning_mae_minutes": round(float(np.mean(start_errors)), 2) if start_errors else None,
        "unsafe_day_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "unsafe_day_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "reference_inside_p10_p90_duration_envelope": round(
            sum(min(r["p10_steps"], r["p90_steps"]) <= r["reference_steps"] <= max(r["p10_steps"], r["p90_steps"])
                for r in rows) / len(rows), 3
        ),
    }


def evaluate(candidates: list[dict], risk: str = "p50") -> dict:
    if risk not in RISK_CASES:
        raise ValueError(f"risk must be one of {RISK_CASES}")
    rows = []
    for candidate in candidates:
        result = early_warning(candidate["date"], risk=risk)
        predicted, reference = result["predicted"], result["reference"]
        rows.append({
            **candidate,
            "predicted_steps": predicted["violation_steps"],
            "reference_steps": reference["violation_steps"],
            "p10_steps": result["cases"]["p10"]["violation_steps"],
            "p90_steps": result["cases"]["p90"]["violation_steps"],
            "predicted_peak_pu": predicted["max_vm_pu"],
            "reference_peak_pu": reference["max_vm_pu"],
            "predicted_start": predicted["first_unsafe"],
            "reference_start": reference["first_unsafe"],
        })
    cloudy = max(rows, key=lambda row: row["challenge_score"])
    ordered = sorted(rows, key=lambda row: row["challenge_score"])
    third = max(1, len(ordered) // 3)
    groups = {
        "clear_or_stable": ordered[:third],
        "mixed": ordered[third:-third] or ordered[:third],
        "cloudy_or_variable": ordered[-third:],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "risk_band": risk,
        "selection_rule": "maximum P10-P90 width plus normalized P50 ramping, using forecast-only data",
        "selected_cloudy_day": cloudy["date"],
        "aggregate": summarise(rows),
        "segments": {name: summarise(group) for name, group in groups.items()},
        "days": rows,
        "limitations": [
            "Reference solar is ERA5/PVWatts-derived, not measured panel production.",
            "Demand and upstream voltage are same-calendar-day 2019 historical proxies.",
            "Results apply to an adapted benchmark feeder, not a surveyed Mathura feeder.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=1, help="evaluate every Nth eligible day")
    parser.add_argument("--max-days", type=int, default=None, help="optional transparent runtime cap")
    parser.add_argument("--risk", choices=RISK_CASES, default="p50")
    args = parser.parse_args()
    candidates = eligible_dates()[::max(args.stride, 1)]
    if args.max_days is not None:
        candidates = candidates[:args.max_days]
    report = evaluate(candidates, risk=args.risk)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cloudy_date = report["selected_cloudy_day"]
    cloudy = early_warning(cloudy_date, risk=args.risk)
    (RESULTS_DIR / f"early_warning_cloudy_{cloudy_date}.json").write_text(
        json.dumps(cloudy, separators=(",", ":")), encoding="utf-8"
    )
    print(json.dumps(report["aggregate"], indent=2))
    print(f"selected cloudy/variable day: {cloudy_date}")


if __name__ == "__main__":
    main()
