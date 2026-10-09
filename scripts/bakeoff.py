"""Bake-offs: run every candidate for one component on identical data and apply the pre-registered rule.

Usage:  python -m scripts.bakeoff solar        (rules: docs/DECISIONS.md)

Writes data/results/bakeoff_<component>.json with the candidates, their scores, the split, the rule,
the winner, the git hash and a timestamp. Losing candidates stay in the record.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from engine import config
from ml import solar_v2
from ml.conformal import conformal_q

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"
_SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "summer", 4: "summer", 5: "summer",
           6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon", 10: "post_monsoon", 11: "post_monsoon"}


def season(index: pd.DatetimeIndex) -> pd.Index:
    return index.month.map(_SEASON)


def decide_median(rows: list[dict], *, reference: str, margin: float) -> dict:
    """Rows are ordered simplest first. S = simplest row with MAE below the reference's; the lowest-WIS row
    wins only if its WIS is at least `margin` below S's, else S wins. Nothing below the reference: it stays."""
    ref_mae = next(r["mae_p50"] for r in rows if r["name"] == reference)
    beating = [r for r in rows if r["name"] != reference and r["mae_p50"] < ref_mae]
    if not beating:
        return {"winner": reference, "simplest_beating_reference": None,
                "reason": f"no candidate has MAE below {reference}"}
    simplest = beating[0]
    best = min(beating, key=lambda r: r["wis"])
    gain = 1 - best["wis"] / simplest["wis"]
    winner = best if gain >= margin else simplest
    return {"winner": winner["name"], "simplest_beating_reference": simplest["name"],
            "lowest_wis": best["name"], "wis_gain_over_simplest": round(gain, 4),
            "reason": f"lowest-WIS gain over the simplest candidate beating {reference} is {gain:.1%} "
                      f"({'meets' if gain >= margin else 'below'} the {margin:.0%} margin)"}


def decide_interval(rows: list[dict], *, band: tuple[float, float]) -> dict:
    """Lowest WIS among rows inside `band` in every season; else the smallest worst-season distance from the centre."""
    lo, hi = band
    centre = (lo + hi) / 2
    in_band = [r for r in rows if all(lo <= c <= hi for c in r["by_season"].values())]
    if in_band:
        winner = min(in_band, key=lambda r: r["wis"])
        reason = "lowest WIS among candidates inside the band in every season"
    else:
        winner = min(rows, key=lambda r: max(abs(c - centre) for c in r["by_season"].values()))
        reason = "no candidate inside the band in every season; smallest worst-season miss"
    return {"winner": winner["name"], "in_band": [r["name"] for r in in_band], "reason": reason}


def point_with_conformal(point: pd.Series, y: pd.Series, daylight: pd.Series, days: pd.DatetimeIndex, *,
                         window: int = 60, calibration_start: str | None = None) -> pd.DataFrame:
    """A median-only forecast gets the same rolling split-conformal interval as solar v2."""
    frame = pd.DataFrame({"p10": point, "p50": point, "p90": point})
    return solar_v2.rolling_conformal(frame, y, daylight, days, window=window, calibration_start=calibration_start)


def _git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def record(component: str, result: dict, *, rule: str, split: str, out_dir: Path = RESULTS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"bakeoff_{component}.json"
    payload = {"component": component, "rule": rule, "split": split, **result,
               "git_hash": _git_hash(), "timestamp": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


# ---- solar -------------------------------------------------------------------------------------------------

SOLAR_SPLIT = "train 2024-01..10; conformal pool from 2024-11; test 2025 daylight hours (identical mask)"
SOLAR_MEDIAN_RULE = ("simplest candidate with MAE below Round 1 = S; lowest WIS wins if >= 3% below S's WIS, "
                     "else S; nothing below Round 1 keeps Round 1")
SOLAR_INTERVAL_RULE = ("lowest WIS among candidates with 78-82% coverage in every season; else smallest "
                       "worst-season distance from 80%")


def _quantile_models(X: pd.DataFrame, target: pd.Series, rows: pd.Series) -> dict:
    return {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **solar_v2.PARAMS)
            .fit(X.loc[rows, solar_v2.FEATURES], target[rows]) for q, a in solar_v2.QUANTILES.items()}


def _lgbm_direct(X: pd.DataFrame, y: pd.Series, train: pd.Series) -> pd.DataFrame:
    rows = train & X["pv_mean"].notna()
    models = _quantile_models(X, y, rows)
    raw = pd.DataFrame({q: m.predict(X[solar_v2.FEATURES]) for q, m in models.items()}, index=X.index)
    raw[:] = np.sort(raw.to_numpy(), axis=1)
    out = raw.clip(lower=0)
    out[X["clearsky_ghi"] <= 0] = 0.0
    out[X["pv_mean"].isna()] = np.nan
    return out


def _bias_corrected(X: pd.DataFrame, y: pd.Series, train: pd.Series) -> pd.Series:
    rows = train & X["pv_mean"].notna() & y.notna()
    b, a = np.polyfit(X.loc[rows, "pv_mean"], y[rows], 1)
    out = (a + b * X["pv_mean"]).clip(lower=0)
    return out.where(X["clearsky_ghi"] > 0, 0.0)


def _round1(y_index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.read_parquet(config.PROCESSED_DIR / "solar_forecast_2025.parquet")
    return frame[["p10", "p50", "p90"]].reindex(y_index)


def _scores(pred: pd.DataFrame, y: pd.Series, mask: pd.Series) -> dict:
    base = solar_v2.evaluate(pred, y, mask, {})
    base.pop("gate_g3_passes", None)
    by = {}
    for s, idx in pd.Series(mask[mask].index, index=mask[mask].index).groupby(season(mask[mask].index)):
        m = pd.Series(False, index=mask.index)
        m[idx.index] = True
        sc = solar_v2.evaluate(pred, y, m, {})
        by[s] = {"mae_p50": sc["mae_p50"], "wis": sc["wis"], "coverage": sc["p10_p90_coverage"], "n": sc["n"]}
    return {**base, "by_season": by}


def _per_hour_conformal(raw: pd.DataFrame, y: pd.Series, day: pd.Series, days, window: int, start: str):
    out = raw.copy()
    for h in sorted(set(raw.index.hour[day.to_numpy()])):
        hour = day & (raw.index.hour == h)
        part = solar_v2.rolling_conformal(raw, y, hour, days, window=window, min_points=30, calibration_start=start)
        out.loc[hour, ["p10", "p90"]] = part.loc[hour, ["p10", "p90"]]
    return out


def solar(district: str = "mathura") -> dict:
    X, y, avail, used = solar_v2.load_dataset(district)
    day = X["clearsky_ghi"] > 0
    train = day & (X.index < "2024-11-01")
    start, days = "2024-11-01", pd.date_range("2025-01-01", "2025-12-31")

    best_match = solar_v2._pv(solar_v2.read_previous_runs(solar_v2.raw_path(None, district)).reindex(y.index))
    residual_raw = solar_v2.predict(solar_v2.fit(X, y, train), X)
    raw = {                                                     # simplest first; frames before any widening
        "persistence": pd.DataFrame({q: y.shift(24) for q in ("p10", "p50", "p90")}),
        "round1": _round1(y.index),
        "physics_best_match": pd.DataFrame({q: best_match for q in ("p10", "p50", "p90")}),
        "physics_mean_5nwp": pd.DataFrame({q: X["pv_mean"] for q in ("p10", "p50", "p90")}),
        "bias_corrected_mean": pd.DataFrame({q: _bias_corrected(X, y, train) for q in ("p10", "p50", "p90")}),
        "lgbm_direct": _lgbm_direct(X, y, train),
        "lgbm_residual": residual_raw,
    }
    final = {n: (f if n == "round1" else solar_v2.rolling_conformal(f, y, day, days, window=60, calibration_start=start))
             for n, f in raw.items()}
    mask = day & (X.index.year == 2025) & y.notna()
    for f in final.values():
        mask &= f["p50"].notna()
    median_rows = [{"name": n, **_scores(f, y, mask)} for n, f in final.items()]
    median = decide_median(median_rows, reference="round1", margin=0.03)

    win = raw[median["winner"]]
    if median["winner"] == "round1":
        win = raw["round1"]
    widened = {
        "raw_quantiles": win,
        "round1_scale_2.5": win.assign(p10=(win["p50"] - 2.5 * (win["p50"] - win["p10"])).clip(lower=0),
                                       p90=win["p50"] + 2.5 * (win["p90"] - win["p50"])),
        **{f"conformal_{w}d": solar_v2.rolling_conformal(win, y, day, days, window=w, calibration_start=start)
           for w in (30, 60, 120)},
        "conformal_per_hour_60d": _per_hour_conformal(win, y, day, days, 60, start),
    }
    interval_rows = []
    for n, f in widened.items():
        sc = _scores(f, y, mask)
        interval_rows.append({"name": n, "wis": sc["wis"], "mae_p50": sc["mae_p50"],
                              "p10_p90_coverage": sc["p10_p90_coverage"],
                              "by_season": {s: v["coverage"] for s, v in sc["by_season"].items()}})
    interval = decide_interval(interval_rows, band=(0.78, 0.82))

    q_end = conformal_q(win[day & win["p50"].notna() & (X.index >= "2025-11-02")],
                        y[day & win["p50"].notna() & (X.index >= "2025-11-02")])
    return {"district": district, "nwp_models_used": used, "mask_hours": int(mask.sum()),
            "median": {"rule": SOLAR_MEDIAN_RULE, **median, "candidates": median_rows},
            "interval": {"rule": SOLAR_INTERVAL_RULE, "median_model": median["winner"], **interval,
                         "candidates": interval_rows},
            "winner": {"median": median["winner"], "interval": interval["winner"]},
            "conformal_q_last_60d_of_2025_raw": round(q_end, 6)}


COMPONENTS = {"solar": (solar, SOLAR_MEDIAN_RULE + " | " + SOLAR_INTERVAL_RULE, SOLAR_SPLIT)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("component", choices=sorted(COMPONENTS))
    args = ap.parse_args(argv)
    fn, rule, split = COMPONENTS[args.component]
    result = fn()
    path = record(args.component, result, rule=rule, split=split)
    print(json.dumps({"winner": result["winner"], "file": str(path.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
