"""Recalibrate the risk probabilities (gate G8) with isotonic regression, strictly out of sample.

Usage:  python -m scripts.calibrate_risk --rule pm10 [--district mathura]

1. Calibration fit: the risk model is fitted on days before 2020-05-01 and predicts 2020-05-01..2020-12-31; an
   isotonic map from predicted probability to observed frequency is fitted on those (predicted, observed) steps.
2. Honest test: the model fitted before 2021-01-01 predicts the 2021 test days (the G8 protocol); the fixed map is
   applied and Brier scores are compared: raw, calibrated, and the base rate.
Writes data/results/risk_calibration_<rule>.json. The API applies the map and sets calibration.reliable only when the
calibrated probabilities beat the base rate on the held-out test.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from engine import config
from engine.archetypes import build
from engine.reliability import backtest, brier, reliability_table
from engine.rules import get_rule

CAL_SPLIT, CAL_END, TEST_SPLIT = "2020-05-01", "2021-01-01", "2021-01-01"
OUT = Path(__file__).resolve().parents[1] / "data" / "results"


def fit_map(pred: np.ndarray, obs: np.ndarray) -> IsotonicRegression:
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(pred.ravel(), obs.ravel().astype(float))


def apply_map(points: dict, p: np.ndarray) -> np.ndarray:
    """Apply a stored isotonic map (piecewise-linear through its thresholds)."""
    return np.interp(np.asarray(p, float), points["x"], points["y"])


def run(rule_id: str, district: str = "mathura", days: int = 40, scenarios: int = 40) -> dict:
    warnings.filterwarnings("ignore")
    base = config.PROCESSED_DIR / "v2"
    load = pd.read_parquet(base / f"load_kw_{district}.parquet")
    pv = pd.read_parquet(base / f"pv_kw_per_kwp_{district}.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / f"upstream_vm_pu_{district}.parquet")["upstream_vm_pu"]
    net, rule = build("benchmark_250", phases="round_robin"), get_rule(rule_id)
    cal = backtest(net, rule, load, pv, up, split=CAL_SPLIT, test_end=CAL_END, n_days=days, n_scenarios=scenarios,
                   return_pairs=True)
    iso = fit_map(cal["pairs"]["predicted"], cal["pairs"]["observed"])
    test = backtest(net, rule, load, pv, up, split=TEST_SPLIT, n_days=days, n_scenarios=scenarios, return_pairs=True)
    pred, obs = test["pairs"]["predicted"], test["pairs"]["observed"]
    points = {"x": [float(x) for x in iso.X_thresholds_], "y": [float(y) for y in iso.y_thresholds_]}
    calibrated = apply_map(points, pred)
    base_rate = float(obs.mean())
    b_raw, b_cal, b_ref = brier(pred, obs), brier(calibrated, obs), brier(np.full_like(pred, base_rate), obs)
    return {
        "rule": rule.id, "district": district, "map": points,
        "calibration_fit": {"split": CAL_SPLIT, "test_end": CAL_END, "days": cal["days"],
                            "observed_unsafe_share": cal["observed_unsafe_share_of_steps"]},
        "held_out_test": {"split": TEST_SPLIT, "days": test["days"], "observed_unsafe_share": round(base_rate, 4),
                          "brier_raw": round(b_raw, 4), "brier_calibrated": round(b_cal, 4), "brier_base_rate": round(b_ref, 4),
                          "skill_raw": round(1 - b_raw / b_ref, 3) if b_ref else None,
                          "skill_calibrated": round(1 - b_cal / b_ref, 3) if b_ref else None,
                          "reliability_calibrated": reliability_table(calibrated, obs)},
        "reliable": bool(b_ref and b_cal < b_ref),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default="pm10")
    ap.add_argument("--district", default="mathura")
    a = ap.parse_args()
    result = run(a.rule, a.district)
    path = OUT / f"risk_calibration_{result['rule']}.json"
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("rule", "reliable")} | {"test": {k: v for k, v in result["held_out_test"].items()
                                                                              if k != "reliability_calibrated"}}, indent=1))


if __name__ == "__main__":
    main()
