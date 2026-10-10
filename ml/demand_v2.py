"""Demand forecast v2: all seasons, holiday flags, conformal intervals, time and district hold-out.

Target: mean kW per home across the meters present, 15-minute (Round 1 used the same quantity).
Two variants are always reported: STRICT (only lagged temperature) and ORACLE (target-day ERA5
temperature, an upper bound on what a good day-ahead temperature forecast could add).

Usage:  python -m ml.demand_v2        (needs data/processed/v2 from scripts/build_data.py)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import holidays
import lightgbm as lgb
import numpy as np
import pandas as pd

from engine import config
from ml.conformal import apply_conformal, conformal_q
from ml.forecast import PARAMS
from ml.metrics import coverage, skill, wis

SLOTS_PER_DAY = 96
EPS = 0.05
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
BASES = ("lag1d", "lag7d", "mean_1d_7d")
WINDOW_DAYS = 14                 # rolling conformal window, chosen on 2020 validation (docs/DECISIONS.md)
REPORT = Path(__file__).resolve().parent / "reports" / "demand_v2.json"
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA",
          9: "SON", 10: "SON", 11: "SON"}


def street_mean(loads: pd.DataFrame, min_meters: int = 5) -> pd.Series:
    """Mean kW per home over the meters present; NaN when fewer than `min_meters` report."""
    mean = loads.mean(axis=1).where(loads.notna().sum(axis=1) >= min_meters)
    return mean.asfreq("15min").rename("kw_per_home")


def baselines(y: pd.Series) -> dict[str, pd.Series]:
    d1, d7 = y.shift(SLOTS_PER_DAY), y.shift(7 * SLOTS_PER_DAY)
    return {"lag1d": d1, "lag7d": d7, "mean_1d_7d": (d1 + d7) / 2}


def holiday_set(years, subdiv: str = "UP") -> set[date]:
    return set(holidays.country_holidays("IN", subdiv=subdiv, years=list(years)).keys())


def _at_issue(trailing: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    """The value of a trailing statistic at the end of the day before each step (when tomorrow's forecast is made)."""
    return trailing.reindex(idx.floor("D") - pd.Timedelta(minutes=15)).to_numpy()


def build_features(y: pd.Series, temp: pd.Series, hol: set, oracle_temp: pd.Series | None = None) -> pd.DataFrame:
    """Every column is known before the target interval begins, except `temp_target` (oracle only)."""
    b = baselines(y)
    same_slot = pd.concat([y.shift(k * SLOTS_PER_DAY) for k in range(1, 8)], axis=1)
    roll7 = same_slot.mean(axis=1).where(same_slot.notna().sum(axis=1) >= 4)
    idx = y.index
    day = pd.Series(idx.date, index=idx)
    prev_day = pd.Series((idx - pd.Timedelta(days=1)).date, index=idx)
    temp = temp.reindex(idx)
    doy = idx.dayofyear.to_numpy()
    X = pd.DataFrame({
        "ratio_1d_7d": np.log((b["lag1d"] + EPS) / (b["lag7d"] + EPS)),
        "ratio_roll7_1d": np.log((roll7 + EPS) / (b["lag1d"] + EPS)),
        "slot": idx.hour * 4 + idx.minute // 15,
        "dow": idx.dayofweek,
        "sin_doy": np.sin(2 * np.pi * doy / 365.25),
        "cos_doy": np.cos(2 * np.pi * doy / 365.25),
        "is_holiday": day.isin(hol).astype(int),
        "is_holiday_prev": prev_day.isin(hol).astype(int),
        "temp_lag_1d": temp.shift(SLOTS_PER_DAY),
        "temp_change_lagged": temp.shift(SLOTS_PER_DAY) - temp.shift(2 * SLOTS_PER_DAY),
        "ratio_2d_1d": np.log((y.shift(2 * SLOTS_PER_DAY) + EPS) / (b["lag1d"] + EPS)),
        "ratio_14d_1d": np.log((y.shift(14 * SLOTS_PER_DAY) + EPS) / (b["lag1d"] + EPS)),
        "yday_mean_ratio": np.log((_at_issue(y.rolling(SLOTS_PER_DAY, min_periods=80).mean(), idx) + EPS) / (b["lag1d"] + EPS)),
        "week_mean_ratio": np.log((_at_issue(y.rolling(7 * SLOTS_PER_DAY, min_periods=500).mean(), idx) + EPS)
                                  / (b["lag1d"] + EPS)),
        "smooth_ratio": np.log((y.rolling(5, min_periods=3).mean().shift(SLOTS_PER_DAY) + EPS) / (b["lag1d"] + EPS)),
        "temp_yday_mean": _at_issue(temp.rolling(SLOTS_PER_DAY, min_periods=80).mean(), idx),
    }, index=idx)
    if oracle_temp is not None:
        X["temp_target"] = oracle_temp.reindex(idx)
    return X


def choose_base(y: pd.Series, upto: pd.Timestamp) -> str:
    b = baselines(y)
    mask = y.index < upto
    return min(BASES, key=lambda n: float((b[n][mask] - y[mask]).abs().mean()))


def _rows(y: pd.Series, temp: pd.Series, hol: set, base_name: str, oracle: bool, district: int):
    X = build_features(y, temp, hol, oracle_temp=temp if oracle else None).assign(district=district)
    base = baselines(y)[base_name]
    target = np.log((y + EPS) / (base + EPS))
    ok = X.notna().all(axis=1) & target.notna() & base.notna()
    return X[ok], target[ok], base[ok], y[ok]


def fit_model(y: pd.Series, temp: pd.Series, hol: set, base_name: str, train_end: pd.Timestamp,
              calib_days: int = 60, params: dict | None = None, oracle: bool = False,
              pool: list[tuple[pd.Series, pd.Series]] = (), window_days: int | None = WINDOW_DAYS) -> dict:
    """Quantile LightGBM on the log-ratio to `base_name`. `pool` adds other districts' rows before the calibration window to the
    training set (district flag 1, 2, ...); calibration always uses `y`'s own last `calib_days`. With `window_days`,
    `predict` widens each day with the conformal amount of the `window_days` before it (rolling window)."""
    X, target, base, yy = _rows(y, temp, hol, base_name, oracle, 0)
    calib_start = train_end - pd.Timedelta(days=calib_days)
    train = X.index < calib_start
    calib = (X.index >= calib_start) & (X.index < train_end)
    Xs, ts = [X[train]], [target[train]]
    for k, (py, pt) in enumerate(pool, start=1):
        PX, ptarget, _, _ = _rows(py, pt, hol, base_name, oracle, k)
        Xs.append(PX[PX.index < calib_start]); ts.append(ptarget[ptarget.index < calib_start])
    Xtr, ttr = pd.concat(Xs), pd.concat(ts)
    p = dict(PARAMS if params is None else params)
    models = {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **p).fit(Xtr, ttr)
              for q, a in QUANTILES.items()}
    model = {"models": models, "base_name": base_name, "oracle": oracle, "columns": list(X.columns),
             "train_end": train_end, "q": 0.0, "window_days": window_days}
    cal = _predict_level(model, X[calib], base[calib])
    model["q"] = conformal_q(cal, yy[calib])
    model["n_train"] = int(len(Xtr))
    return model


def _predict_level(model: dict, X: pd.DataFrame, base: pd.Series) -> pd.DataFrame:
    raw = pd.DataFrame({q: m.predict(X[model["columns"]]) for q, m in model["models"].items()}, index=X.index)
    level = np.exp(raw).mul(base + EPS, axis=0) - EPS
    level[:] = np.sort(level.clip(lower=0).to_numpy(), axis=1)
    return level


def _rolling_conformal(level: pd.DataFrame, actual: pd.Series, window_days: int, q_fixed: float) -> pd.DataFrame:
    """Widen each day by the conformal amount of the `window_days` before it; the fixed amount until enough history."""
    days = level.index.normalize()
    out = []
    for day in days.unique():
        cal = (level.index >= day - pd.Timedelta(days=window_days)) & (level.index < day)
        q = conformal_q(level[cal], actual[cal]) if cal.sum() >= 200 else q_fixed
        out.append(apply_conformal(level[days == day], q, floor=0.0))
    return pd.concat(out)


def predict(model: dict, y: pd.Series, temp: pd.Series, hol: set) -> pd.DataFrame:
    X = build_features(y, temp, hol, oracle_temp=temp if model["oracle"] else None).assign(district=0)
    b = baselines(y)
    ok = X.notna().all(axis=1) & y.notna() & b["lag1d"].notna() & b["lag7d"].notna()
    X, yy = X[ok], y[ok]
    level = _predict_level(model, X, b[model["base_name"]][ok])
    if model.get("window_days"):
        out = _rolling_conformal(level, yy, model["window_days"], model["q"])
    else:
        out = apply_conformal(level, model["q"], floor=0.0)
    out["actual"] = yy
    for n in BASES:
        out[n] = b[n][ok]
    return out


def score(frame: pd.DataFrame) -> dict:
    mae = float((frame["p50"] - frame["actual"]).abs().mean())
    res = {"n": int(len(frame)), "mae_p50": round(mae, 4),
           "coverage": round(coverage(frame["actual"], frame["p10"], frame["p90"]), 3),
           "wis": round(wis(frame["actual"], frame["p10"], frame["p50"], frame["p90"]), 4)}
    base_mae = {n: float((frame[n] - frame["actual"]).abs().mean()) for n in BASES}
    for n, m in base_mae.items():
        res[f"mae_{n}"] = round(m, 4)
        res[f"skill_vs_{n}"] = round(skill(mae, m), 3)
    res["best_baseline"] = min(base_mae, key=base_mae.get)
    res["skill_vs_best_baseline"] = round(skill(mae, min(base_mae.values())), 3)
    return res


def score_by_season(frame: pd.DataFrame) -> dict:
    return {s: score(g) for s, g in frame.groupby(frame.index.month.map(SEASON)) if len(g) > 200}


def _load(district: str) -> tuple[pd.Series, pd.Series]:
    base = config.PROCESSED_DIR / "v2"
    y = street_mean(pd.read_parquet(base / f"load_kw_{district}.parquet"))
    temp = pd.read_parquet(base / f"weather_hourly_{district}.parquet")["temperature_2m"]
    return y, temp.resample("15min").interpolate("time").reindex(y.index)


def main() -> None:
    hol = holiday_set(range(2019, 2022))
    y_m, t_m = _load("mathura")
    y_b, t_b = _load("bareilly")
    train_end = pd.Timestamp("2021-01-01")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "target": "mean kW per home, 15 min",
              "protocols": {}, "gate_g4": {}}
    for variant, oracle in (("strict", False), ("oracle_weather", True)):
        base_name = choose_base(y_m, train_end)
        # Protocol 1: train Mathura (plus Bareilly's rows) before 2021, test Mathura 2021
        m1 = fit_model(y_m, t_m, hol, base_name, train_end, oracle=oracle, pool=[(y_b, t_b)])
        f1 = predict(m1, y_m, t_m, hol)
        test1 = f1[f1.index >= train_end]
        # Protocol 2: train all Mathura, test Bareilly (held-out district)
        m2 = fit_model(y_m, t_m, hol, base_name, y_m.dropna().index.max().floor("D"), oracle=oracle)
        test2 = predict(m2, y_b, t_b, hol)
        report["protocols"][variant] = {
            "base": base_name,
            "time_mathura_2021": {**score(test1), "by_season": score_by_season(test1)},
            "district_bareilly": {**score(test2), "by_season": score_by_season(test2)},
        }
    s = report["protocols"]["strict"]["time_mathura_2021"]
    report["gate_g4"] = {"skill_vs_best_baseline": s["skill_vs_best_baseline"], "coverage": s["coverage"],
                         "passed": bool(s["skill_vs_best_baseline"] >= 0.10 and 0.78 <= s["coverage"] <= 0.82)}
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["gate_g4"], indent=2))


if __name__ == "__main__":
    main()
