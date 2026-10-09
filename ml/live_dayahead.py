"""Day-ahead household demand and grid voltage for tomorrow, anchored to live Uttar Pradesh state demand.

There are no live household meters, so nothing here uses household lags. The shape over the day comes from the CEEW
meters (2019-2021): time of day, weekday, season, UP holidays and temperature. The level comes from `up_ratio`
(ml.up_demand): yesterday's UP state energy against the week before, available live from UPSLDC every day.

Usage:  python -m ml.live_dayahead            evaluate (walk-forward), write the report, train the live models
        python -m ml.live_dayahead --live     tomorrow's forecast for both districts
Design and pre-registered rule: docs/superpowers/specs/2026-10-09-live-demand-voltage-design.md, docs/DECISIONS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from engine import config
from ml import metrics, up_demand
from ml.conformal import conformal_q
from ml.demand_v2 import holiday_set, street_mean
from ml.solar_v2 import save_booster

TARGETS = {"demand": "kW per home", "voltage": "V"}
DISTRICT_IDS = {"mathura": 0, "bareilly": 1}
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
FEATURES_PATTERN = ["slot", "dow", "is_weekend", "sin_doy", "cos_doy", "is_holiday", "is_holiday_prev",
                    "temp", "temp_daymax", "temp_daymean", "district_id"]
FEATURES_LIVE = FEATURES_PATTERN + ["up_ratio"]
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "summer", 4: "summer", 5: "summer",
           6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon", 10: "post_monsoon", 11: "post_monsoon"}
ALPHA = 0.2
MODEL_DIR = Path(__file__).resolve().parent / "models"
MANIFEST = "live_dayahead_manifest.json"
REPORT = Path(__file__).resolve().parent / "reports" / "live_dayahead.json"
PROVENANCE = ("modeled: household pattern learned from CEEW smart meters 2019-2021; level from live UP state demand "
              "(UPSLDC). No live household meters exist.")


def season_of(months) -> np.ndarray:
    return np.array([SEASONS[int(m)] for m in months])


def _params(n_estimators: int) -> dict:
    return {"n_estimators": n_estimators, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 50,
            "verbose": -1, "random_state": 42, "deterministic": True, "force_col_wise": True}


# ---- features ------------------------------------------------------------------------------------------------

def add_features(frame: pd.DataFrame, holidays_set: set) -> pd.DataFrame:
    """Calendar, weather and district columns for a long table with `ts`, `district`, `temp` and `up_ratio`."""
    out = frame.copy()
    ts = out["ts"]
    day = ts.dt.normalize()
    doy = ts.dt.dayofyear.to_numpy()
    out["slot"] = ts.dt.hour * 4 + ts.dt.minute // 15
    out["dow"] = ts.dt.dayofweek
    out["is_weekend"] = (out["dow"] >= 5).astype(int)
    out["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    out["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)
    out["is_holiday"] = day.dt.date.isin(holidays_set).astype(int)
    out["is_holiday_prev"] = (day - pd.Timedelta(days=1)).dt.date.isin(holidays_set).astype(int)
    by_day = out.groupby([out["district"], day])["temp"]
    out["temp_daymax"] = by_day.transform("max")
    out["temp_daymean"] = by_day.transform("mean")
    out["district_id"] = out["district"].map(DISTRICT_IDS)
    out["month"] = ts.dt.to_period("M").astype(str)
    out["season"] = season_of(ts.dt.month)
    return out


def load_all() -> pd.DataFrame:
    """Both districts from data/processed/v2 plus the UP anchor from the Grid-India history."""
    v2 = config.PROCESSED_DIR / "v2"
    ratio = up_demand.up_ratio(up_demand.load_history(up_demand.download_history()))
    frames = []
    for district in DISTRICT_IDS:
        demand = street_mean(pd.read_parquet(v2 / f"load_kw_{district}.parquet"))
        volts = pd.read_parquet(v2 / f"upstream_vm_pu_{district}.parquet")["upstream_vm_pu"].astype(float) * config.NOMINAL_VOLTAGE_V
        temp = pd.read_parquet(v2 / f"weather_hourly_{district}.parquet")["temperature_2m"]
        idx = demand.index.union(volts.index)
        f = pd.DataFrame({"ts": idx, "district": district, "demand": demand.reindex(idx).to_numpy(),
                          "voltage": volts.reindex(idx).to_numpy(),
                          "temp": temp.resample("15min").interpolate("time").reindex(idx).to_numpy()})
        f["up_ratio"] = ratio.reindex(f["ts"].dt.normalize()).to_numpy()
        frames.append(f)
    data = pd.concat(frames, ignore_index=True)
    data = data[data["temp"].notna()]
    return add_features(data, holiday_set(range(2019, 2023)))


# ---- models --------------------------------------------------------------------------------------------------

def fit_quantiles(X: pd.DataFrame, y: pd.Series, n_estimators: int = 300) -> dict:
    return {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **_params(n_estimators)).fit(X, y)
            for q, a in QUANTILES.items()}


def predict_quantiles(models: dict, X: pd.DataFrame) -> pd.DataFrame:
    raw = pd.DataFrame({q: m.predict(X) for q, m in models.items()}, index=X.index)
    raw[:] = np.sort(raw.to_numpy(), axis=1)
    return raw


def climatology(train: pd.DataFrame, test: pd.DataFrame, target: str) -> pd.DataFrame:
    """P10/P50/P90 of the target in the training data by district, month, day type and slot, with coarser fallbacks."""
    def keyed(df):
        return df.assign(daytype=((df["is_weekend"] == 1) | (df["is_holiday"] == 1)).astype(int),
                         mon=df["ts"].dt.month)
    tr, te = keyed(train), keyed(test)
    out = pd.DataFrame(index=test.index, columns=list(QUANTILES), dtype=float)
    for keys in (["district", "mon", "daytype", "slot"], ["district", "daytype", "slot"], ["district", "slot"]):
        table = tr.groupby(keys)[target].quantile(list(QUANTILES.values())).unstack()
        table.columns = list(QUANTILES)
        fill = te[keys].merge(table, left_on=keys, right_index=True, how="left")[list(QUANTILES)]
        fill.index = test.index
        out = out.fillna(fill)
    return out


def walk_forward(data: pd.DataFrame, target: str, features: list[str] | None, *, start_after_months: int = 6,
                 n_estimators: int = 300) -> pd.DataFrame:
    """Out-of-sample P10/P50/P90 for every month after the first `start_after_months`, trained only on earlier
    months (both districts). `features=None` means climatology."""
    rows = data[data[target].notna() & (data[features].notna().all(axis=1) if features else True)]
    months = sorted(rows["month"].unique())
    parts = []
    for month in months[start_after_months:]:
        train, test = rows[rows["month"] < month], rows[rows["month"] == month]
        if features is None:
            pred = climatology(train, test, target)
        else:
            pred = predict_quantiles(fit_quantiles(train[features], train[target], n_estimators), test[features])
        parts.append(pred.assign(month=month, season=test["season"], district=test["district"]))
    return pd.concat(parts)


def mondrian_widen(raw: pd.DataFrame, y: pd.Series, *, min_points: int = 500) -> pd.DataFrame:
    """Widen each month's interval by split-conformal scores of earlier months in the same season (all earlier months
    when the season has fewer than `min_points`). Months are processed in order, so no month sees its own errors."""
    out = raw.copy()
    out["cal_pool"] = "none"
    for month in sorted(raw["month"].unique()):
        now = raw["month"] == month
        earlier = raw["month"] < month
        same = earlier & (raw["season"] == raw.loc[now, "season"].iloc[0])
        pool, label = (same, "season") if same.sum() >= min_points else (earlier, "all")
        if pool.sum() < min_points:
            continue
        q = conformal_q(raw[pool], y[pool], ALPHA)
        out.loc[now, "p10"] = np.minimum(raw.loc[now, "p10"] - q, raw.loc[now, "p50"])
        out.loc[now, "p90"] = np.maximum(raw.loc[now, "p90"] + q, raw.loc[now, "p50"])
        out.loc[now, "cal_pool"] = label
    return out


def score(pred: pd.DataFrame, y: pd.Series) -> dict:
    y = y.reindex(pred.index)
    res = {"n": int(len(pred)), "mae": round(float((pred["p50"] - y).abs().mean()), 4),
           "coverage": round(metrics.coverage(y, pred["p10"], pred["p90"]), 3),
           "wis": round(metrics.wis(y, pred["p10"], pred["p50"], pred["p90"]), 4)}
    res["by_season"] = {s: round(metrics.coverage(y[g.index], g["p10"], g["p90"]), 3) for s, g in pred.groupby("season")}
    res["mae_by_season"] = {s: round(float((g["p50"] - y[g.index]).abs().mean()), 4) for s, g in pred.groupby("season")}
    res["mae_by_district"] = {d: round(float((g["p50"] - y[g.index]).abs().mean()), 4) for d, g in pred.groupby("district")}
    return res


def _meets_coverage(s: dict) -> bool:
    return 0.78 <= s["coverage"] <= 0.82 and all(0.70 <= c <= 0.90 for c in s["by_season"].values())


def decide(rows: dict) -> dict:
    """The pre-registered rule (docs/DECISIONS.md, live day-ahead demand and voltage)."""
    live, clim, pattern = rows["live_anchored"], rows["climatology"], rows["pattern_only"]
    if live["mae"] <= 0.9 * clim["mae"] and live["mae"] < pattern["mae"] and _meets_coverage(live):
        return {"adopted": "live_anchored", "reason": "MAE at least 10% below climatology and below pattern-only, "
                                                       "coverage inside the bands"}
    passing = {n: s for n, s in rows.items() if _meets_coverage(s)}
    if passing:
        best = min(passing, key=lambda n: passing[n]["mae"])
        return {"adopted": best, "reason": "live-anchored model failed the rule; best candidate meeting the coverage rule"}
    best = min(rows, key=lambda n: rows[n]["mae"])
    return {"adopted": best, "reason": "no candidate meets the coverage rule; lowest MAE reported with its miss"}


# ---- final models and live forecast ----------------------------------------------------------------------------

def train_final(data: pd.DataFrame, *, model_dir: Path = MODEL_DIR, widths: dict | None = None,
                decisions: dict | None = None, n_estimators: int = 300) -> dict:
    """Fit pattern-only and live-anchored models on all data and write them with a checksummed manifest."""
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"model_type": "LightGBM quantiles, no household lags, Mondrian (per-season) split-conformal",
                "trained_at": datetime.now(timezone.utc).isoformat(), "provenance": PROVENANCE,
                "features": {"pattern_only": FEATURES_PATTERN, "live_anchored": FEATURES_LIVE},
                "files": {}, "sha256": {}, "widths": widths or {}, "decisions": decisions or {},
                "units": TARGETS}
    for target in TARGETS:
        for variant, feats in (("pattern_only", FEATURES_PATTERN), ("live_anchored", FEATURES_LIVE)):
            rows = data[data[target].notna() & data[feats].notna().all(axis=1)]
            models = fit_quantiles(rows[feats], rows[target], n_estimators)
            for q, m in models.items():
                name = f"live_dayahead_{target}_{variant}_{q}.txt"
                manifest["files"][f"{target}/{variant}/{q}"] = name
                manifest["sha256"][name] = save_booster(m, model_dir / name)
    (model_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def forecast_temperature(district: str, target: date) -> pd.Series:
    """Tomorrow's hourly 2 m temperature from the Open-Meteo forecast, interpolated to 15 minutes."""
    site = config.SITES[district]
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=60, params={
        "latitude": site.latitude, "longitude": site.longitude, "hourly": "temperature_2m", "timezone": config.TIMEZONE,
        "start_date": target.isoformat(), "end_date": (target + timedelta(days=1)).isoformat()})
    r.raise_for_status()
    hourly = r.json()["hourly"]
    s = pd.Series(hourly["temperature_2m"], index=pd.to_datetime(hourly["time"]), dtype=float)
    return s.resample("15min").interpolate("time").loc[target.isoformat()]


def current_ratio(target: date) -> float:
    """`up_ratio` for the target day from the Grid-India history plus the live UPSLDC record; NaN if a day is missing."""
    live = up_demand.LIVE_PATH
    energy = up_demand.daily_energy(pd.read_parquet(live)["demand_mw"]) if live.exists() else pd.Series(dtype=float)
    ratio = up_demand.up_ratio(up_demand.combined_energy(up_demand.load_history(), energy))
    return float(ratio.get(pd.Timestamp(target), np.nan))


def live_forecast(district: str, target: date | None = None, *, temperature: pd.Series | None = None,
                  ratio: float | None = None, model_dir: Path = MODEL_DIR, holidays_set: set | None = None) -> dict:
    """96 quarter-hour P10/P50/P90 values of household demand and grid voltage for `target` (default: tomorrow)."""
    target = target or (datetime.now(timezone(timedelta(hours=5, minutes=30))).date() + timedelta(days=1))
    temperature = temperature if temperature is not None else forecast_temperature(district, target)
    ratio = current_ratio(target) if ratio is None else ratio
    used = bool(np.isfinite(ratio))
    variant = "live_anchored" if used else "pattern_only"
    manifest = json.loads((model_dir / MANIFEST).read_text(encoding="utf-8"))
    frame = pd.DataFrame({"ts": pd.date_range(target.isoformat(), periods=96, freq="15min"), "district": district,
                          "temp": temperature.to_numpy()[:96], "up_ratio": ratio if used else np.nan})
    hol = holidays_set if holidays_set is not None else holiday_set([target.year - 1, target.year])
    X = add_features(frame, hol)
    season = X["season"].iloc[0]
    out = {"date": target.isoformat(), "district": district, "provenance": PROVENANCE,
           "anchor": {"used": used, "up_ratio": round(ratio, 4) if used else None,
                      "note": "level anchored to live UP state demand" if used else
                              "pattern only: the UP anchor needs eight straight recorded days (scripts/record_up_demand.py)"}}
    for target_name, unit in TARGETS.items():
        preds = {}
        for q in QUANTILES:
            name = manifest["files"][f"{target_name}/{variant}/{q}"]
            path = model_dir / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
                raise RuntimeError(f"checksum mismatch for {name}")
            preds[q] = lgb.Booster(model_file=str(path)).predict(X[manifest["features"][variant]])
        p = pd.DataFrame(preds)
        p[:] = np.sort(p.to_numpy(), axis=1)
        width = manifest["widths"].get(target_name, {}).get(variant, {}).get(season, 0.0)
        p["p10"] = np.minimum(p["p10"] - width, p["p50"])
        p["p90"] = np.maximum(p["p90"] + width, p["p50"])
        if target_name == "demand":
            p = p.clip(lower=0)
        out[target_name] = {"unit": unit, "model": variant, "interval_width_season": season,
                            "points": [{"t": ts.strftime("%H:%M"), **{q: round(float(r[q]), 4) for q in QUANTILES}}
                                       for ts, (_, r) in zip(X["ts"], p.iterrows())]}
    return out


# ---- evaluation ---------------------------------------------------------------------------------------------------

def evaluate(data: pd.DataFrame, n_estimators: int = 300) -> tuple[dict, dict]:
    """Walk-forward bake-off for both targets on identical rows; returns the report and the per-season widths."""
    report, widths = {"generated_at": datetime.now(timezone.utc).isoformat(), "targets": {}}, {}
    for target in TARGETS:
        rows = data[data[target].notna() & data["up_ratio"].notna()]               # identical rows for every candidate
        y = rows[target]
        raw = {"climatology": walk_forward(rows, target, None, n_estimators=n_estimators),
               "pattern_only": walk_forward(rows, target, FEATURES_PATTERN, n_estimators=n_estimators),
               "live_anchored": walk_forward(rows, target, FEATURES_LIVE, n_estimators=n_estimators)}
        widened = {n: mondrian_widen(r, y) for n, r in raw.items()}
        scores = {n: score(w, y) for n, w in widened.items()}
        widths[target] = {n: {s: round(float(conformal_q(raw[n][raw[n].season == s], y[raw[n][raw[n].season == s].index], ALPHA)), 6)
                              for s in raw[n]["season"].unique()} for n in ("pattern_only", "live_anchored")}
        held = {}
        train, test = rows[rows.district == "mathura"], rows[rows.district == "bareilly"]
        for name, feats in (("pattern_only", FEATURES_PATTERN), ("live_anchored", FEATURES_LIVE)):
            f = [c for c in feats if c != "district_id"]
            p = predict_quantiles(fit_quantiles(train[f], train[target], n_estimators), test[f])
            held[name] = round(float((p["p50"] - test[target]).abs().mean()), 4)
        clim_f = climatology(train.assign(district="bareilly"), test, target)          # Mathura's pattern for Bareilly
        held["climatology"] = round(float((clim_f["p50"] - test[target]).abs().mean()), 4)
        report["targets"][target] = {
            "unit": TARGETS[target], "rows": int(len(rows)), "months_tested": sorted(raw["live_anchored"]["month"].unique().tolist()),
            "walk_forward": scores,
            "skill_vs_climatology": {n: round(1 - s["mae"] / scores["climatology"]["mae"], 3) for n, s in scores.items()},
            "held_out_district_mae": held, "decision": decide(scores)}
    return report, widths


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="forecast tomorrow for both districts")
    args = ap.parse_args(argv)
    if args.live:
        for district in DISTRICT_IDS:
            out = live_forecast(district)
            print(json.dumps({"date": out["date"], "district": district, "anchor": out["anchor"],
                              **{t: {"model": out[t]["model"], "peak_p50": max(p["p50"] for p in out[t]["points"]),
                                     "min_p50": min(p["p50"] for p in out[t]["points"])} for t in TARGETS}}, indent=2))
        return
    data = load_all()
    report, widths = evaluate(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    train_final(data, widths=widths, decisions={t: r["decision"] for t, r in report["targets"].items()})
    print(json.dumps({t: {"decision": r["decision"], "skill_vs_climatology": r["skill_vs_climatology"],
                          "coverage": {n: s["coverage"] for n, s in r["walk_forward"].items()}}
                      for t, r in report["targets"].items()}, indent=2))


if __name__ == "__main__":
    main()
