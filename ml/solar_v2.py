"""Solar forecast v2 (B2): multi-model NWP ensemble, residual quantile model, rolling split-conformal.

Pipeline for each hour:
  1. every available NWP model's day-ahead irradiance (Open-Meteo previous-runs, `previous_day1`) goes through the same
     pvlib PVWatts chain as the truth, giving one physical PV forecast per model;
  2. the mean, spread (min, max, std) of those forecasts plus mean cloud, mean irradiance and the clear-sky irradiance
     are the features;
  3. LightGBM quantile models predict the *residual* of truth over the ensemble mean (P10, P50, P90);
  4. the interval is widened by split-conformal scores of earlier out-of-sample errors from the same season
     (method chosen by the bake-off, see CONFORMAL_METHOD).

The truth is ERA5-driven PV (a reference proxy, not measured rooftop output); see the model manifest.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from engine import config, profiles
from ml.conformal import conformal_q

MODELS = ("gfs_global", "icon_global", "gem_global", "meteofrance_arpege_world", "ecmwf_ifs025")
CANDIDATE_MODELS = MODELS + ("jma_gsm", "ukmo_global_deterministic_10km")
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
FEATURES = ["pv_mean", "pv_min", "pv_max", "pv_std", "ghi_mean", "cloud_mean", "clearsky_ghi", "hour", "doy", "n_models"]
PARAMS = {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20, "verbose": -1,
          "random_state": 42, "deterministic": True, "force_col_wise": True}
FIRST_MODEL_TABLE = config.PROCESSED_DIR / "solar_forecast_2025.parquet"   # the first (Round 1) model's 2025 forecast
AVAILABILITY_MIN = 0.95              # gate G2
# Bake-off of 9 Oct 2026 (docs/DECISIONS.md, data/results/bakeoff_solar.json): no window keeps 78-82% coverage in
# every season; 30 days has the smallest worst-season miss (winter 74.9%). 60 and 120 days stay callable via `window`.
CONFORMAL_WINDOW_DAYS = 30
# Round 2 of the interval bake-off (docs/DECISIONS.md): one width per season, learnt from every earlier day of that
# season, fixes the winter under-coverage (74.9% -> 79.5%). The 30-day width stays as the fallback and the monitor's
# recent check.
CONFORMAL_METHOD = "by_season_all_earlier"
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "summer", 4: "summer", 5: "summer",
           6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon", 10: "post_monsoon", 11: "post_monsoon"}
FILL = {"wind_speed_10m": 5.0, "temperature_2m": 30.0, "diffuse_radiation": 0.0,
        "direct_normal_irradiance": 0.0, "shortwave_radiation": 0.0}


@lru_cache(maxsize=1)
def first_model_mae(path: Path = FIRST_MODEL_TABLE) -> float:
    """Gate G3 reference: the first solar model's 2025 MAE, recomputed from its committed forecast table.

    Scored the way ml/forecast.py scored it: the table's whole-hour rows (the 15-minute rows between them are
    interpolations written for the dashboard), daylight hours (clear-sky GHI above zero), the median against the
    table's own `actual` column (ERA5-driven PV, the same truth solar v2 uses on these hours). That is 4,414 hours of
    2025 and reproduces the first model's report (0.0396). Averaging the 15-minute rows mixes in interpolated values
    and does not."""
    table = pd.read_parquet(path)
    hours = table[table.index.minute == 0]
    day = profiles.clearsky_ghi(hours.index) > 0
    return round(float((hours.loc[day, "p50"] - hours.loc[day, "actual"]).abs().mean()), 4)


def raw_path(model: str | None, district: str = "mathura") -> Path:
    """`None` is Open-Meteo's default (best-match) blend that Round 1 used."""
    stem = "dayahead" if model is None else f"dayahead_{model}"
    return config.RAW_DIR / f"{stem}_{district}_2024_2025.json"


def read_previous_runs(path: Path) -> pd.DataFrame:
    """Hourly frame with the `_previous_day1` suffix removed; unavailable hours are NaN."""
    df = profiles.read_weather(path)
    df.columns = [c.replace("_previous_day1", "") for c in df.columns]
    return df.apply(pd.to_numeric, errors="coerce")


def availability(frames: dict[str, pd.DataFrame], test_year: int = 2025) -> pd.DataFrame:
    """Gate G2: share of non-null irradiance hours since the model's first valid hour, and in the test year."""
    rows = []
    for name, df in frames.items():
        ghi = df["shortwave_radiation"]
        first = ghi.first_valid_index()
        since = float(ghi[first:].notna().mean()) if first is not None else 0.0
        in_year = float(ghi[ghi.index.year == test_year].notna().mean())
        rows.append({"model": name, "first_valid": first, "nonnull_since_first": round(since, 4),
                     f"nonnull_{test_year}": round(in_year, 4), "passes": since >= AVAILABILITY_MIN and in_year >= AVAILABILITY_MIN})
    return pd.DataFrame(rows).set_index("model")


def _pv(frame: pd.DataFrame) -> pd.Series:
    """Physical PV forecast for one model; NaN wherever the model had no irradiance."""
    ok = frame["shortwave_radiation"].notna()
    return profiles.pv_hourly(frame.ffill().fillna(FILL)).where(ok)


def ensemble_features(frames: dict[str, pd.DataFrame], site: config.Site | None = None) -> pd.DataFrame:
    """Features on the union hourly index of the frames. Models missing at an hour are ignored at that hour."""
    index = next(iter(frames.values())).index
    pv = pd.DataFrame({m: _pv(f.reindex(index)) for m, f in frames.items()}, index=index)
    ghi = pd.DataFrame({m: f.reindex(index)["shortwave_radiation"] for m, f in frames.items()})
    cloud = pd.DataFrame({m: f.reindex(index)["cloud_cover"] for m, f in frames.items()})
    return pd.DataFrame({
        "pv_mean": pv.mean(axis=1), "pv_min": pv.min(axis=1), "pv_max": pv.max(axis=1), "pv_std": pv.std(axis=1),
        "ghi_mean": ghi.mean(axis=1), "cloud_mean": cloud.mean(axis=1),
        "clearsky_ghi": profiles.clearsky_ghi(index, site).to_numpy(),
        "hour": index.hour, "doy": index.dayofyear, "n_models": pv.notna().sum(axis=1),
    }, index=index)


def fit(X: pd.DataFrame, y: pd.Series, mask: pd.Series) -> dict[str, lgb.LGBMRegressor]:
    """Quantile models on the residual y - pv_mean over the rows where the ensemble exists."""
    rows = mask & X["pv_mean"].notna()
    resid = (y - X["pv_mean"])[rows]
    return {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **PARAMS).fit(X.loc[rows, FEATURES], resid) for q, a in QUANTILES.items()}


def predict(models: dict[str, lgb.LGBMRegressor], X: pd.DataFrame) -> pd.DataFrame:
    """P10/P50/P90 in kW per installed kW; sorted, never negative, zero at night. NaN where there is no ensemble."""
    raw = pd.DataFrame({q: m.predict(X[FEATURES]) for q, m in models.items()}, index=X.index)
    raw[:] = np.sort(raw.to_numpy(), axis=1)
    out = raw.add(X["pv_mean"], axis=0).clip(lower=0)
    out[X["clearsky_ghi"] <= 0] = 0.0
    out[X["pv_mean"].isna()] = np.nan
    return out


def rolling_conformal(pred: pd.DataFrame, y: pd.Series, daylight: pd.Series, days: pd.DatetimeIndex, *,
                      window: int = 60, min_points: int = 50, alpha: float = 0.2, calibration_start: str | None = None) -> pd.DataFrame:
    """Widen each day's interval by the conformal score of the previous `window` days of out-of-sample errors.

    Only days strictly before the target day are used, so the interval is available the evening before.
    `calibration_start` excludes in-sample rows (the model's own training period) from the pool.
    """
    out = pred.copy()
    dates = pd.Series(pred.index.normalize(), index=pred.index)
    pool = daylight & y.notna() & pred["p50"].notna()
    if calibration_start is not None:
        pool &= pred.index >= calibration_start
    for d in days:
        today = (dates == d) & daylight & pred["p50"].notna()
        sel = pool & (dates < d) & (dates >= d - pd.Timedelta(days=window))
        if not today.any() or sel.sum() < min_points:
            continue
        q = conformal_q(pred[sel], y[sel], alpha)
        out.loc[today, "p10"] = (pred.loc[today, "p10"] - q).clip(lower=0)
        out.loc[today, "p90"] = pred.loc[today, "p90"] + q
    return out


def season_of_index(index: pd.DatetimeIndex) -> np.ndarray:
    return np.array([SEASONS[int(m)] for m in index.month])


def sky_class(X: pd.DataFrame) -> pd.Series:
    """Forecast sky per hour from the NWP ensemble: clear (clearness above 0.8), partly, cloudy (below 0.5), night."""
    k = X["ghi_mean"] / X["clearsky_ghi"].where(X["clearsky_ghi"] > 0)
    out = np.select([X["clearsky_ghi"] <= 0, k > 0.8, k < 0.5], ["night", "clear", "cloudy"], "partly")
    return pd.Series(out, index=X.index, name="sky")


def _conformal_from_scores(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    k = min(n, int(np.ceil((n + 1) * (1 - alpha))))
    return float(np.sort(scores)[k - 1])


def _pool_window(pred: pd.DataFrame, y: pd.Series, daylight: pd.Series, calibration_start: str | None):
    dates = pd.Series(pred.index.normalize(), index=pred.index)
    pool = daylight & y.notna() & pred["p50"].notna()
    if calibration_start is not None:
        pool &= pred.index >= calibration_start
    return dates, pool


def rolling_conformal_groups(pred: pd.DataFrame, y: pd.Series, daylight: pd.Series, days: pd.DatetimeIndex,
                             groups: pd.Series, *, window: int | None = 30, min_points: int = 50, alpha: float = 0.2,
                             calibration_start: str | None = None) -> pd.DataFrame:
    """Like `rolling_conformal`, but each group (sky class, season...) gets its own width from its own earlier hours.
    `window=None` uses every earlier day. A group with fewer than `min_points` earlier hours uses the all-hours pool."""
    out = pred.copy()
    dates, pool = _pool_window(pred, y, daylight, calibration_start)
    for d in days:
        today = (dates == d) & daylight & pred["p50"].notna()
        if not today.any():
            continue
        earlier = pool & (dates < d) & ((dates >= d - pd.Timedelta(days=window)) if window else True)
        for g in groups[today].unique():
            rows = today & (groups == g)
            sel = earlier & (groups == g)
            if sel.sum() < min_points:
                sel = earlier
            if sel.sum() < min_points:
                continue
            q = conformal_q(pred[sel], y[sel], alpha)
            out.loc[rows, "p10"] = (pred.loc[rows, "p10"] - q).clip(lower=0)
            out.loc[rows, "p90"] = pred.loc[rows, "p90"] + q
    return out


def rolling_conformal_scaled(pred: pd.DataFrame, y: pd.Series, daylight: pd.Series, days: pd.DatetimeIndex, *,
                             window: int = 30, min_points: int = 50, alpha: float = 0.2,
                             calibration_start: str | None = None) -> pd.DataFrame:
    """Errors measured in units of the model's own P10-P90 spread, so hours the model is unsure about widen more."""
    out = pred.copy()
    dates, pool = _pool_window(pred, y, daylight, calibration_start)
    spread = (pred["p90"] - pred["p10"]).clip(lower=1e-3)
    scores = np.maximum(pred["p10"] - y, y - pred["p90"]) / spread
    for d in days:
        today = (dates == d) & daylight & pred["p50"].notna()
        sel = pool & (dates < d) & (dates >= d - pd.Timedelta(days=window))
        if not today.any() or sel.sum() < min_points:
            continue
        q = _conformal_from_scores(scores[sel].to_numpy(), alpha)
        out.loc[today, "p10"] = (pred.loc[today, "p10"] - q * spread[today]).clip(lower=0)
        out.loc[today, "p90"] = pred.loc[today, "p90"] + q * spread[today]
    return out


def evaluate(pred: pd.DataFrame, y: pd.Series, mask: pd.Series, baselines: dict[str, pd.Series]) -> dict:
    from ml import metrics
    t = mask & pred["p50"].notna()
    yt = y[t]
    mae = float((pred["p50"][t] - yt).abs().mean())
    scores = {"n": int(t.sum()), "mae_p50": round(mae, 4),
              "p10_p90_coverage": round(metrics.coverage(yt, pred["p10"][t], pred["p90"][t]), 3),
              "wis": round(metrics.wis(yt, pred["p10"][t], pred["p50"][t], pred["p90"][t]), 4)}
    for name, series in baselines.items():
        b = float((series[t] - yt).abs().mean())
        scores[f"mae_{name}"] = round(b, 4)
        scores[f"skill_vs_{name}"] = round(metrics.skill(mae, b), 3)
    scores["gate_g3_passes"] = bool(mae < first_model_mae())
    return scores


def save_booster(model: lgb.LGBMRegressor, path: Path) -> str:
    """Save with LF line endings (as .gitattributes stores ml/models/*.txt) and return the SHA-256 of those bytes,
    so the manifest hash still matches after a fresh checkout on any platform."""
    model.booster_.save_model(str(path))
    data = path.read_bytes().replace(b"\r\n", b"\n")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def write_manifest(path: Path, *, models_used: list[str], scores: dict, window: int, files: dict, sha256: dict, conformal_q: float,
                   conformal_q_by_season: dict | None = None) -> None:
    path.write_text(json.dumps({
        "conformal_method": CONFORMAL_METHOD, "conformal_q_by_season": conformal_q_by_season or {},
        "model_type": "LightGBM residual quantiles over a multi-NWP physical ensemble, rolling split-conformal",
        "model_version": "2.0.0", "quantiles": list(QUANTILES), "model_files": files, "model_sha256": sha256,
        "nwp_models": models_used, "conformal_window_days": window, "conformal_q": round(conformal_q, 6),
        "feature_names": FEATURES,
        "truth": "ERA5 reanalysis through pvlib PVWatts (reference proxy, not measured rooftop PV)",
        "scores_2025": scores,
        "limitations": ["Coverage is tuned to the ERA5-driven proxy, not to rooftop meters.",
                        "Open-Meteo previous-runs history for some models starts in 2024 only.",
                        "conformal_q is the value at the end of the training year; the nightly monitor refreshes it."],
    }, indent=2), encoding="utf-8")


MODEL_DIR = Path(__file__).resolve().parent / "models"
REPORT = Path(__file__).resolve().parent / "reports" / "solar_v2.json"


def load_dataset(district: str = "mathura") -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, list[str]]:
    """Ensemble features X, ERA5-driven truth y, the availability table (gate G2) and the NWP models that passed it."""
    site = config.SITES[district]
    candidates = {m: read_previous_runs(raw_path(m, district)) for m in CANDIDATE_MODELS if raw_path(m, district).exists()}
    if not candidates:
        raise RuntimeError(f"no multi-model weather files in {config.RAW_DIR} (dayahead_<model>_{district}_2024_2025.json); "
                           "run python -m scripts.download_solar_v2")
    avail = availability(candidates)
    used = [m for m in MODELS if m in avail.index and bool(avail.loc[m, "passes"])]
    if len(used) < 3:
        raise RuntimeError(f"gate G2 leaves only {len(used)} NWP models; need at least 3: {list(avail.index[avail.passes])}")
    truth = profiles.read_weather(config.RAW_DIR / f"era5_{district}_2024_2025.json")
    y = profiles.pv_hourly(truth, site)
    X = ensemble_features({m: candidates[m].reindex(y.index) for m in used}, site)
    return X, y, avail, used


def run(district: str = "mathura", window: int = CONFORMAL_WINDOW_DAYS) -> dict:
    """Train on 2024-01..10, use 2024-11..12 only as the first conformal pool, score on daylight hours of 2025."""
    X, y, avail, used = load_dataset(district)
    day = X["clearsky_ghi"] > 0
    train = day & (X.index < "2024-11-01")
    test = day & (X.index.year == 2025)
    models = fit(X, y, train)
    raw = predict(models, X)
    seasons = pd.Series(season_of_index(X.index), index=X.index)
    pred = rolling_conformal_groups(raw, y, day, pd.date_range("2025-01-01", "2025-12-31"), seasons, window=None,
                                    calibration_start="2024-11-01")
    best = read_previous_runs(raw_path(None, district)).reindex(y.index)
    baselines = {"persistence": y.shift(24), "physics_only_best_match": _pv(best), "physics_only_ensemble": X["pv_mean"]}
    scores = evaluate(pred, y, test, baselines)
    scores["interval_without_conformal"] = evaluate(raw, y, test, {})["p10_p90_coverage"]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    files, digests = {}, {}
    for q, m in models.items():
        f = MODEL_DIR / f"solar_v2_{q}.txt"
        files[q], digests[q] = f.name, save_booster(m, f)
    last = pd.Timestamp("2025-12-31")
    pool = day & raw["p50"].notna() & (X.index >= last - pd.Timedelta(days=window - 1)) & (X.index <= last + pd.Timedelta(days=1))
    q_now = conformal_q(raw[pool], y[pool], 0.2)
    out_of_sample = day & raw["p50"].notna() & y.notna() & (X.index >= "2024-11-01")
    q_by_season = {s: round(conformal_q(raw[out_of_sample & (seasons == s)], y[out_of_sample & (seasons == s)], 0.2), 6)
                   for s in sorted(seasons[out_of_sample].unique())}
    write_manifest(MODEL_DIR / "solar_v2_manifest.json", models_used=used, scores=scores, window=window,
                   files=files, sha256=digests, conformal_q=q_now, conformal_q_by_season=q_by_season)
    report = {"availability": json.loads(avail.reset_index().to_json(orient="records", date_format="iso")),
              "nwp_models_used": used, "scores_2025": scores, "model_sha256": digests, "conformal_q_end_of_2025": round(q_now, 6),
              "conformal_method": CONFORMAL_METHOD, "conformal_q_by_season": q_by_season}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pred.assign(actual=y).loc[test[test].index].to_parquet(config.PROCESSED_DIR / "solar_forecast_v2_2025.parquet")
    return report


if __name__ == "__main__":
    print(json.dumps(run()["scores_2025"], indent=2))
