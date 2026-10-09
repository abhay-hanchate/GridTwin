"""B3: foundation-model benchmark. Chronos-2 with covariates against the solar v2 LightGBM pipeline, same splits.

The foundation model is used as a benchmark only. It is adopted only if its weighted interval score is at least 5%
better on 2025 AND the deployment can supply yesterday's observed PV (it uses a 14-day context of observations, which
the LightGBM pipeline does not need). Requires `pip install -r requirements-ml.txt`.
"""
from __future__ import annotations

import pandas as pd

from ml import metrics

ADOPTION_WIS_GAIN = 0.05
CONTEXT_HOURS = 24 * 14
COVARIATES = ("pv_mean", "ghi_mean", "cloud_mean")


def build_frames(X: pd.DataFrame, y: pd.Series, days: pd.DatetimeIndex, covariates=COVARIATES,
                 context_hours: int = CONTEXT_HOURS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One series per target day: observations and covariates up to 23:00 the day before, covariates for the 24 hours of the day."""
    cov = X[list(covariates)].ffill().fillna(0.0)
    past, future = [], []
    for d in days:
        ctx = X.index[(X.index >= d - pd.Timedelta(hours=context_hours)) & (X.index < d)]
        fut = X.index[(X.index >= d) & (X.index < d + pd.Timedelta(days=1))]
        if len(ctx) < context_hours or len(fut) < 24:
            continue
        past.append(pd.DataFrame({"id": str(d.date()), "timestamp": ctx, "target": y.loc[ctx].to_numpy()}).join(cov.loc[ctx].reset_index(drop=True)))
        future.append(pd.DataFrame({"id": str(d.date()), "timestamp": fut}).join(cov.loc[fut].reset_index(drop=True)))
    if not past:
        return pd.DataFrame(columns=["id", "timestamp", "target", *covariates]), pd.DataFrame(columns=["id", "timestamp", *covariates])
    return pd.concat(past, ignore_index=True), pd.concat(future, ignore_index=True)


def chronos_forecast(past: pd.DataFrame, future: pd.DataFrame, pipeline=None, batch_days: int = 60) -> pd.DataFrame:
    """P10/P50/P90 per hour from Chronos-2. `pipeline` can be injected (tests); otherwise amazon/chronos-2 is loaded."""
    if pipeline is None:
        import torch
        from chronos import Chronos2Pipeline
        pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cuda" if torch.cuda.is_available() else "cpu")
    ids = past["id"].unique()
    parts = []
    for i in range(0, len(ids), batch_days):
        chunk = ids[i:i + batch_days]
        parts.append(pipeline.predict_df(past[past.id.isin(chunk)], future_df=future[future.id.isin(chunk)], id_column="id",
                                         timestamp_column="timestamp", target="target", prediction_length=24,
                                         quantile_levels=[0.1, 0.5, 0.9]))
    out = pd.concat(parts).rename(columns={"0.1": "p10", "0.5": "p50", "0.9": "p90"}).set_index("timestamp")[["p10", "p50", "p90"]]
    return out.clip(lower=0)


def compare(y: pd.Series, mask: pd.Series, candidates: dict[str, pd.DataFrame], reference: str) -> dict:
    """Scores for every candidate on the identical mask, plus the adoption decision against the reference."""
    scores = {}
    for name, pred in candidates.items():
        t = mask & pred["p50"].notna()
        scores[name] = {"n": int(t.sum()), "mae_p50": round(float((pred["p50"][t] - y[t]).abs().mean()), 4),
                        "coverage": round(metrics.coverage(y[t], pred["p10"][t], pred["p90"][t]), 3),
                        "wis": round(metrics.wis(y[t], pred["p10"][t], pred["p50"][t], pred["p90"][t]), 4)}
    ref = scores[reference]["wis"]
    for name, s in scores.items():
        s["wis_gain_vs_reference"] = round(1 - s["wis"] / ref, 3)
        s["adopt"] = bool(name != reference and s["wis_gain_vs_reference"] >= ADOPTION_WIS_GAIN)
    return scores


def run(district: str = "mathura") -> dict:
    """Chronos-2 against the solar v2 pipeline on daylight hours of 2025. Needs the raw files and requirements-ml.txt."""
    import json
    from ml import solar_v2
    X, y, _, used = solar_v2.load_dataset(district)
    day = X["clearsky_ghi"] > 0
    test = day & (X.index.year == 2025)
    raw = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-11-01")), X)
    v2 = solar_v2.rolling_conformal(raw, y, day, pd.date_range("2025-01-01", "2025-12-31"), calibration_start="2024-11-01")
    past, future = build_frames(X, y, pd.date_range("2025-01-01", "2025-12-31"))
    chronos = chronos_forecast(past, future).reindex(X.index)
    scores = compare(y, test, {"solar_v2_lightgbm": v2, "chronos2_with_covariates": chronos}, reference="solar_v2_lightgbm")
    report = {"scores_2025": scores, "nwp_models_used": used,
              "caveat": "Chronos-2 sees the previous 14 days of observed PV; the LightGBM pipeline needs none. "
                        "Adoption therefore also requires a live source of yesterday's PV."}
    out = solar_v2.REPORT.with_name("solar_benchmark.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run()["scores_2025"], indent=2))
