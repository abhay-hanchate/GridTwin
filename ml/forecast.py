"""Solar and household-demand forecasts with LightGBM quantile models (P10 / P50 / P90).

Solar: inputs are genuine day-ahead weather forecasts (Open-Meteo Previous Runs API,
"previous_day1" = issued the day before). Target is solar output modelled from ERA5
reanalysis, an independent reference proxy rather than measured panel output. Train 2024,
test 2025.
(The Open-Meteo historical-forecast and archive APIs return identical values for 2021+,
so they cannot be used as forecast vs truth.)
Demand: average Mathura household load, 15-minute. Train May-Oct 2019, test Nov-Dec 2019.

Usage:  python -m ml.forecast
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import config, profiles  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
MODEL_DIR = ML_DIR / "models"
REPORT = ML_DIR / "reports" / "metrics.json"
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
PARAMS = {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20, "verbose": -1}
RANDOM_SEED = 42
PARAMS.update({"random_state": RANDOM_SEED, "deterministic": True, "force_col_wise": True})


def _fit_quantiles(X: pd.DataFrame, y: pd.Series, name: str) -> dict:
    models = {}
    for q, alpha in QUANTILES.items():
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **PARAMS).fit(X, y)
        m.booster_.save_model(str(MODEL_DIR / f"{name}_{q}.txt"))
        models[q] = m
    return models


def _predict_unsorted(models: dict, X: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({q: m.predict(X) for q, m in models.items()}, index=X.index)


def _predict(models: dict, X: pd.DataFrame) -> pd.DataFrame:
    out = _predict_unsorted(models, X).clip(lower=0)
    # Quantile models are trained separately; sort so P10 <= P50 <= P90 always holds.
    out[:] = np.sort(out.to_numpy(), axis=1)
    return out


def _band_scale(pred: pd.DataFrame, actual: pd.Series, target: float = 0.8) -> float:
    """Conformal-style calibration: widen or narrow the P10-P90 band around P50 so that it
    covers `target` of the held-out calibration data."""
    for k in np.arange(0.5, 6.01, 0.05):
        lo = pred["p50"] - k * (pred["p50"] - pred["p10"])
        hi = pred["p50"] + k * (pred["p90"] - pred["p50"])
        if ((actual >= lo) & (actual <= hi)).mean() >= target:
            return float(k)
    return 6.0


def _apply_scale(pred: pd.DataFrame, k: float, floor: float = 0.0) -> pd.DataFrame:
    out = pred.copy()
    out["p10"] = (pred["p50"] - k * (pred["p50"] - pred["p10"])).clip(lower=floor)
    out["p90"] = pred["p50"] + k * (pred["p90"] - pred["p50"])
    return out


def _scores(actual: pd.Series, pred: pd.DataFrame, baselines: dict) -> dict:
    mae = float((pred["p50"] - actual).abs().mean())
    scores = {"mae_p50": round(mae, 4),
              "p10_p90_coverage": round(float(((actual >= pred["p10"]) & (actual <= pred["p90"])).mean()), 3)}
    for name, series in baselines.items():
        b = float((series - actual).abs().mean())
        scores[f"mae_{name}"] = round(b, 4)
        scores[f"skill_vs_{name}"] = round(1 - mae / b, 3)
    return scores


def _read_hourly(name: str) -> pd.DataFrame:
    return profiles.read_weather(config.RAW_DIR / name)


def solar_features(fc: pd.DataFrame) -> pd.DataFrame:
    idx = fc.index
    return pd.DataFrame({
        "fc_pv": profiles.pv_hourly(fc).to_numpy(),
        "fc_ghi": fc["shortwave_radiation"].to_numpy(),
        "fc_cloud": fc["cloud_cover"].to_numpy(),
        "fc_temp": fc["temperature_2m"].to_numpy(),
        "clearsky_ghi": profiles.clearsky_ghi(idx).to_numpy(),
        "hour": idx.hour, "doy": idx.dayofyear,
    }, index=idx)


def solar_training_data() -> tuple[pd.DataFrame, pd.Series, dict[str, pd.Series]]:
    """Return the solar feature matrix, reference target and disjoint temporal masks."""
    fc = _read_hourly("dayahead_mathura_2024_2025.json")
    fc.columns = [c.replace("_previous_day1", "") for c in fc.columns]
    fc = fc.dropna()
    obs = _read_hourly("era5_mathura_2024_2025.json").loc[fc.index]
    X = solar_features(fc)
    y = profiles.pv_hourly(obs)
    daylight = X["clearsky_ghi"] > 0
    masks = {
        "train": daylight & (X.index < "2024-11-01"),
        "calibration": daylight & (X.index >= "2024-11-01") & (X.index.year == 2024),
        "test": daylight & (X.index.year == 2025),
    }
    return X, y, masks


def demand_features(y: pd.Series, temperature: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Build leakage-safe demand features and return yesterday's load baseline.

    Every feature is available before the target interval begins. In particular, target-day
    archive temperature is never used: the temperature terms are delayed by one and two days.
    """
    eps = 0.05
    lag_1d, lag_7d = y.shift(96), y.shift(672)
    temp_lag_1d, temp_lag_2d = temperature.shift(96), temperature.shift(192)
    X = pd.DataFrame({
        "ratio_1d_7d": np.log((lag_1d + eps) / (lag_7d + eps)),
        "slot": y.index.hour * 4 + y.index.minute // 15,
        "dow": y.index.dayofweek,
        "temp_lag_1d": temp_lag_1d,
        "temp_change_lagged": temp_lag_1d - temp_lag_2d,
    }, index=y.index)
    return X, lag_1d


def train_solar() -> dict:
    X, y, masks = solar_training_data()
    day = X["clearsky_ghi"] > 0
    fit, calib, test = masks["train"], masks["calibration"], masks["test"]

    models = _fit_quantiles(X[fit], y[fit], "solar")
    pred = pd.DataFrame(0.0, index=X.index, columns=list(QUANTILES))
    pred.loc[day] = _predict(models, X[day]).to_numpy()
    k = _band_scale(pred[calib], y[calib])
    pred.loc[day] = _apply_scale(pred[day], k).to_numpy()

    scores = _scores(y[test], pred[test], {
        "persistence": y.shift(24, freq="h").reindex(y.index)[test],   # same hour yesterday
        "physics_only": X.loc[test, "fc_pv"],                          # pvlib on the raw forecast
    })
    hourly = pred.assign(actual=y)[X.index.year == 2025]
    hourly.resample("15min").interpolate("time").astype("float32").to_parquet(
        config.PROCESSED_DIR / "solar_forecast_2025.parquet")
    return scores


def train_demand() -> dict:
    loads = pd.read_parquet(config.PROCESSED_DIR / "load_kw.parquet").loc["2019"]
    # Keep the full regular 15-minute grid so that shift(96) is exactly one day even across gaps.
    y = loads.mean(axis=1).asfreq("15min").rename("kw_per_home")
    weather = pd.read_parquet(config.PROCESSED_DIR / "weather_hourly.parquet")
    temp = weather["temperature_2m"].resample("15min").interpolate("time").reindex(y.index)
    eps = 0.05
    # Scale-free design: predict the log-ratio to the same slot yesterday, with no absolute
    # level as input. Summer demand is ~3x winter demand, and trees cannot extrapolate levels.
    X, lag_1d = demand_features(y, temp)
    keep = X.notna().all(axis=1) & y.notna() & lag_1d.notna()
    X, y, lag_1d = X[keep], y[keep], lag_1d[keep]
    log_ratio = np.log((y + eps) / (lag_1d + eps))
    fit = X.index < "2019-10-01"
    calib = (X.index >= "2019-10-01") & (X.index < "2019-11-01")
    test = X.index >= "2019-11-01"

    models = _fit_quantiles(X[fit], log_ratio[fit], "demand")
    raw = _predict_unsorted(models, X)
    pred = (np.exp(raw).mul(lag_1d + eps, axis=0) - eps).clip(lower=0)
    pred[:] = np.sort(pred.to_numpy(), axis=1)
    pred = _apply_scale(pred, _band_scale(pred[calib], y[calib]))
    scores = _scores(y[test], pred[test], {"persistence": lag_1d[test]})
    pred.assign(actual=y)[test].astype("float32").to_parquet(config.PROCESSED_DIR / "demand_forecast_2019.parquet")
    return scores


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "solar": {"target": "kW per installed kW, daytime hours", "inputs": "day-ahead forecast",
                  "truth": "ERA5 reanalysis", "train": "2024", "test": "2025",
                  **train_solar()},
        "demand": {"target": "average household kW, 15-minute", "train": "May-Oct 2019", "test": "Nov-Dec 2019",
                   "inputs": "lagged demand, calendar and temperature delayed by at least one day",
                   "leakage_guard": "no target-day archive weather is used",
                   **train_demand()},
    }
    REPORT.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
