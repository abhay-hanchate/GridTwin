"""Recalibrate the risk probabilities (gate G8) with isotonic regression, strictly out of sample.

Usage:  python -m scripts.calibrate_risk --rule pm10 [--district mathura]

Both districts by default (the G8 protocol of plan task P5.3):
1. Calibration fit: each district's risk model is fitted on days before 2020-05-01 and predicts 2020-05-01..2020-12-31;
   one isotonic map from predicted probability to observed frequency is fitted on the pooled (predicted, observed) steps.
2. Honest test: each district's model fitted before 2021-01-01 predicts its 2021 test days; the fixed map is applied
   and Brier scores are compared, pooled and per district: raw, calibrated, and the base rate of the test steps.
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


DISTRICT_DAYS = {"mathura": 40, "bareilly": 60}      # test days per district: Mathura 2021 ends on 20 Feb


def _inputs(district: str):
    base = config.PROCESSED_DIR / "v2"
    load = pd.read_parquet(base / f"load_kw_{district}.parquet")
    pv = pd.read_parquet(base / f"pv_kw_per_kwp_{district}.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / f"upstream_vm_pu_{district}.parquet")["upstream_vm_pu"]
    return load, pv, up


def _scores(pred: np.ndarray, calibrated: np.ndarray, obs: np.ndarray) -> dict:
    base_rate = float(obs.mean())
    b_raw, b_cal, b_ref = brier(pred, obs), brier(calibrated, obs), brier(np.full_like(pred, base_rate), obs)
    return {"observed_unsafe_share": round(base_rate, 4), "brier_raw": round(b_raw, 4),
            "brier_calibrated": round(b_cal, 4), "brier_base_rate": round(b_ref, 4),
            "skill_raw": round(1 - b_raw / b_ref, 3) if b_ref else None,
            "skill_calibrated": round(1 - b_cal / b_ref, 3) if b_ref else None}


def run(rule_id: str, districts: dict[str, int] | None = None, scenarios: int = 40, cal_days: int = 40) -> dict:
    """Both districts by default (the G8 protocol of plan task P5.3); one pooled isotonic map per rule."""
    warnings.filterwarnings("ignore")
    districts = DISTRICT_DAYS if districts is None else districts
    net, rule = build("benchmark_250", phases="round_robin"), get_rule(rule_id)
    cal_pred, cal_obs, tests, cal_info = [], [], {}, {}
    for district, days in districts.items():
        load, pv, up = _inputs(district)
        cal = backtest(net, rule, load, pv, up, split=CAL_SPLIT, test_end=CAL_END, n_days=cal_days,
                       n_scenarios=scenarios, return_pairs=True)
        cal_pred.append(cal["pairs"]["predicted"]); cal_obs.append(cal["pairs"]["observed"])
        cal_info[district] = {"days": cal["days"], "observed_unsafe_share": cal["observed_unsafe_share_of_steps"]}
        tests[district] = backtest(net, rule, load, pv, up, split=TEST_SPLIT, n_days=days, n_scenarios=scenarios,
                                   return_pairs=True)
    iso = fit_map(np.concatenate(cal_pred), np.concatenate(cal_obs))
    points = {"x": [float(x) for x in iso.X_thresholds_], "y": [float(y) for y in iso.y_thresholds_]}
    per_district = {}
    for district, t in tests.items():
        pred, obs = t["pairs"]["predicted"], t["pairs"]["observed"]
        per_district[district] = {"days": t["days"], **_scores(pred, apply_map(points, pred), obs)}
    pred = np.concatenate([t["pairs"]["predicted"] for t in tests.values()])
    obs = np.concatenate([t["pairs"]["observed"] for t in tests.values()])
    calibrated = apply_map(points, pred)
    pooled = _scores(pred, calibrated, obs)
    return {
        "rule": rule.id, "districts": list(districts), "map": points,
        "calibration_fit": {"split": CAL_SPLIT, "test_end": CAL_END, "by_district": cal_info},
        "held_out_test": {"split": TEST_SPLIT, "days": sum(t["days"] for t in tests.values()), **pooled,
                          "by_district": per_district,
                          "reliability_calibrated": reliability_table(calibrated, obs)},
        "reliable": bool(pooled["brier_base_rate"] and pooled["brier_calibrated"] < pooled["brier_base_rate"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default="pm10")
    ap.add_argument("--district", default=None, help="one district only (default: both, the G8 protocol)")
    a = ap.parse_args()
    result = run(a.rule, None if a.district is None else {a.district: DISTRICT_DAYS[a.district]})
    path = OUT / f"risk_calibration_{result['rule']}.json"
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("rule", "reliable")} | {"test": {k: v for k, v in result["held_out_test"].items()
                                                                              if k != "reliability_calibrated"}}, indent=1))


if __name__ == "__main__":
    main()
