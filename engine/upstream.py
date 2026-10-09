"""Day-ahead stochastic model of the voltage arriving at the transformer (A3), and its bake-off.

Every candidate turns history into whole-day sample paths (n x 96, pu of 230 V) for a target date, using only what
the operator knows the evening before: the calendar and yesterday's mean voltage. `day_z` (n,) lets the scenario
generator couple the day-level draw to solar and demand through its copula; without it the draw is random.

Candidates (pre-registered in docs/DECISIONS.md, simplest first):
  climatology         whole training days from the same calendar month
  analog_days         whole training days whose previous-day mean is closest to yesterday's
  ar1_shape           monthly mean + AR(1) day deviation + (month, weekend) shape + AR(1) slot residual
  lgbm_day_quantiles  LightGBM quantiles of the day mean + a same-month training day's intra-day shape

Usage:  python -m engine.upstream             (evaluation report of the chosen model, ml/reports/upstream_v2.json)
        python -m engine.upstream --bakeoff   (all candidates, data/results/bakeoff_upstream.json)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SLOTS = 96
MIN_VALID_SLOTS = 80
LOW, HIGH = 0.80, 1.20                   # physical clip of a sampled path, pu
MIN_POOL = 5                             # widen the month window until a pool has at least this many days


# ---- day table -----------------------------------------------------------------------------------------------

def day_table(series: pd.Series) -> pd.DataFrame:
    """Usable days x 96 slots. A day is usable with at least 80 valid slots; short gaps are filled within the day."""
    s = series.asfreq("15min")
    rows = {}
    for d, g in s.groupby(s.index.normalize()):
        v = g.to_numpy(dtype=float)
        if len(v) != SLOTS or np.isfinite(v).sum() < MIN_VALID_SLOTS:
            continue
        rows[d] = pd.Series(v).interpolate(limit_direction="both").to_numpy()
    if not rows:
        return pd.DataFrame(columns=range(SLOTS), dtype=float)
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def previous_day_means(table: pd.DataFrame) -> pd.Series:
    """Mean of the calendar day before each usable day; NaN when that day is not usable."""
    means = table.mean(axis=1)
    return means.reindex(table.index - pd.Timedelta(days=1)).set_axis(table.index)


def _month_window(index: pd.DatetimeIndex, month: int, width: int) -> np.ndarray:
    dist = np.minimum((index.month - month) % 12, (month - index.month) % 12)
    return np.asarray(dist <= width)


def _draw_rows(pool: np.ndarray, pool_means: np.ndarray, n: int, rng: np.random.Generator,
               day_z: np.ndarray | None) -> np.ndarray:
    """Indices into `pool`: random, or, with day_z, the day whose mean sits at quantile Phi(z) of the pool."""
    if day_z is None:
        return pool[rng.integers(len(pool), size=n)]
    order = pool[np.argsort(pool_means, kind="stable")]
    u = stats.norm.cdf(np.asarray(day_z, float))
    return order[np.minimum((u * len(order)).astype(int), len(order) - 1)]


def _require(table: pd.DataFrame, minimum: int = 30) -> None:
    if len(table) < minimum:
        raise ValueError(f"need at least {minimum} usable days to fit an upstream-voltage model, got {len(table)}")


# ---- candidates ----------------------------------------------------------------------------------------------

@dataclass
class Climatology:
    days: pd.DataFrame
    name: str = "climatology"

    @classmethod
    def fit(cls, series: pd.Series) -> "Climatology":
        table = day_table(series)
        _require(table)
        return cls(table)

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator,
               day_z: np.ndarray | None = None) -> np.ndarray:
        date = pd.Timestamp(date)
        for width in range(7):
            pool = np.flatnonzero(_month_window(self.days.index, date.month, width))
            if len(pool) >= MIN_POOL:
                break
        rows = _draw_rows(pool, self.days.to_numpy().mean(axis=1)[pool], n, rng, day_z)
        return np.clip(self.days.to_numpy()[rows], LOW, HIGH)


@dataclass
class AnalogDays:
    days: pd.DataFrame
    prev: pd.Series
    k: int = 30
    name: str = "analog_days"

    @classmethod
    def fit(cls, series: pd.Series, k: int = 30) -> "AnalogDays":
        table = day_table(series)
        prev = previous_day_means(table)
        table, prev = table[prev.notna()], prev[prev.notna()]
        _require(table)
        return cls(table, prev, k)

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator,
               day_z: np.ndarray | None = None) -> np.ndarray:
        date = pd.Timestamp(date)
        for width in range(1, 7):
            window = np.flatnonzero(_month_window(self.days.index, date.month, width))
            if len(window) >= self.k:
                break
        distance = np.abs(self.prev.to_numpy()[window] - prev_day_mean)
        pool = window[np.argsort(distance, kind="stable")[: self.k]]
        rows = _draw_rows(pool, self.days.to_numpy().mean(axis=1)[pool], n, rng, day_z)
        return np.clip(self.days.to_numpy()[rows], LOW, HIGH)


def _ar1(x: np.ndarray) -> tuple[float, float]:
    """Least-squares AR(1) coefficient and innovation standard deviation over consecutive finite pairs."""
    a, b = x[:-1], x[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    phi = float((a * b).sum() / (a * a).sum()) if len(a) > 2 and (a * a).sum() > 0 else 0.0
    phi = float(np.clip(phi, -0.99, 0.99))
    resid = b - phi * a
    return phi, float(resid.std()) if len(resid) > 2 else 0.0


@dataclass
class AR1Shape:
    month_mean: dict
    phi: float
    sigma_day: float
    shape: dict
    resid_phi: float
    resid_sigma: float
    global_shape: np.ndarray = field(default_factory=lambda: np.zeros(SLOTS))
    name: str = "ar1_shape"

    @classmethod
    def fit(cls, series: pd.Series) -> "AR1Shape":
        table = day_table(series)
        _require(table)
        day_mean = table.mean(axis=1)
        month_mean = {int(m): float(v) for m, v in day_mean.groupby(day_mean.index.month).mean().items()}
        dev = pd.Series([day_mean[d] - month_mean[d.month] for d in day_mean.index], index=day_mean.index)
        dev = dev.reindex(pd.date_range(dev.index.min(), dev.index.max(), freq="D"))   # gaps break the pairs
        phi, sigma_day = _ar1(dev.to_numpy())
        centred = table.sub(day_mean, axis=0)
        key = [(d.month, int(d.dayofweek >= 5)) for d in table.index]
        shape = {k: g.mean(axis=0).to_numpy() for k, g in centred.groupby(pd.Series(key, index=table.index))}
        resid = centred.to_numpy() - np.vstack([shape[k] for k in key])
        r_phi, r_sigma = _ar1(np.concatenate([np.r_[r, np.nan] for r in resid]))
        return cls(month_mean, phi, sigma_day, shape, r_phi, r_sigma, centred.mean(axis=0).to_numpy())

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator,
               day_z: np.ndarray | None = None) -> np.ndarray:
        date = pd.Timestamp(date)
        fallback = float(np.mean(list(self.month_mean.values())))
        mu = self.month_mean.get(date.month, fallback)
        mu_prev = self.month_mean.get((date - pd.Timedelta(days=1)).month, mu)
        shock = rng.normal(0, 1, n) if day_z is None else np.asarray(day_z, float)
        day_mean = mu + self.phi * (prev_day_mean - mu_prev) + self.sigma_day * shock
        shape = self.shape.get((date.month, int(date.dayofweek >= 5)), self.global_shape)
        resid = np.zeros((n, SLOTS))
        resid[:, 0] = rng.normal(0, self.resid_sigma / np.sqrt(max(1e-9, 1 - self.resid_phi ** 2)), n)
        for t in range(1, SLOTS):
            resid[:, t] = self.resid_phi * resid[:, t - 1] + rng.normal(0, self.resid_sigma, n)
        return np.clip(day_mean[:, None] + shape[None, :] + resid, LOW, HIGH)


QUANTILE_LEVELS = (0.02, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.98)
LGBM_PARAMS = {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 15, "min_child_samples": 20,
               "verbose": -1, "random_state": 42, "deterministic": True, "force_col_wise": True}


def _day_features(date: pd.Timestamp, prev_mean: float, prev_max: float, prev_std: float) -> list[float]:
    doy = date.dayofyear
    return [prev_mean, prev_max, prev_std, np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25),
            float(date.dayofweek >= 5)]


@dataclass
class LgbmDayQuantiles:
    models: list
    shapes: pd.DataFrame                 # usable training days x 96, each minus its own mean
    name: str = "lgbm_day_quantiles"

    @classmethod
    def fit(cls, series: pd.Series) -> "LgbmDayQuantiles":
        import lightgbm as lgb
        table = day_table(series)
        _require(table)
        before = table.reindex(table.index - pd.Timedelta(days=1)).set_axis(table.index)
        ok = before.notna().all(axis=1)
        rows = []
        for d in table.index[ok]:
            v = before.loc[d].to_numpy()
            rows.append(_day_features(d, v.mean(), v.max(), v.std()))
        X = np.array(rows)
        y = table[ok].mean(axis=1).to_numpy()
        _require(table[ok])
        models = [lgb.LGBMRegressor(objective="quantile", alpha=a, **LGBM_PARAMS).fit(X, y) for a in QUANTILE_LEVELS]
        return cls(models, table.sub(table.mean(axis=1), axis=0))

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator,
               day_z: np.ndarray | None = None, prev_day: np.ndarray | None = None) -> np.ndarray:
        """`prev_day` (96,) gives yesterday's maximum and spread; without it they come from the shape climatology."""
        date = pd.Timestamp(date)
        if prev_day is not None:
            p_max, p_std = float(np.nanmax(prev_day)), float(np.nanstd(prev_day))
        else:
            spread = self.shapes.to_numpy()
            p_max, p_std = prev_day_mean + float(spread.max(axis=1).mean()), float(spread.std(axis=1).mean())
        x = np.array([_day_features(date, prev_day_mean, p_max, p_std)])
        q = np.sort([m.predict(x)[0] for m in self.models])
        u = rng.uniform(size=n) if day_z is None else stats.norm.cdf(np.asarray(day_z, float))
        day_mean = np.interp(u, QUANTILE_LEVELS, q)
        for width in range(7):
            pool = np.flatnonzero(_month_window(self.shapes.index, date.month, width))
            if len(pool) >= MIN_POOL:
                break
        shapes = self.shapes.to_numpy()[pool[rng.integers(len(pool), size=n)]]
        return np.clip(day_mean[:, None] + shapes, LOW, HIGH)


CANDIDATES = {c.name: c for c in (Climatology, AnalogDays, AR1Shape, LgbmDayQuantiles)}
# Model of record: winner of the pre-registered bake-off run 9 Oct 2026 (docs/DECISIONS.md, data/results/bakeoff_upstream.json).
UpstreamModel = LgbmDayQuantiles


# ---- evaluation ----------------------------------------------------------------------------------------------

def crps_samples(samples: np.ndarray, y: float) -> float:
    """Sample CRPS: E|X - y| - 0.5 E|X - X'| (the second term from the sorted samples, exact for the sample)."""
    x = np.sort(np.asarray(samples, float))
    n = len(x)
    spread = 2.0 * np.sum((2 * np.arange(1, n + 1) - n - 1) * x) / (n * n)
    return float(np.mean(np.abs(x - y)) - 0.5 * spread)


def evaluate(model, series: pd.Series, n: int = 200, seed: int = 0) -> dict:
    """Score day-ahead paths on every usable day whose previous day is also usable (yesterday's mean is known)."""
    table = day_table(series)
    prev = previous_day_means(table)
    rng = np.random.default_rng(seed)
    hits, crps_max, crps_mean, slot_cov = [], [], [], []
    for d in table.index[prev.notna()]:
        actual = table.loc[d].to_numpy()
        kwargs = {}
        if isinstance(model, LgbmDayQuantiles):
            kwargs["prev_day"] = table.loc[d - pd.Timedelta(days=1)].to_numpy()
        paths = model.sample(d, n, float(prev[d]), rng, **kwargs)
        peak = paths.max(axis=1)
        lo, hi = np.quantile(peak, [0.1, 0.9])
        hits.append(lo <= actual.max() <= hi)
        crps_max.append(crps_samples(peak, actual.max()))
        crps_mean.append(crps_samples(paths.mean(axis=1), actual.mean()))
        q_lo, q_hi = np.quantile(paths, [0.1, 0.9], axis=0)
        slot_cov.append(np.mean((actual >= q_lo) & (actual <= q_hi)))
    if not hits:
        return {"days": 0, "day_max_coverage_80": float("nan"), "crps_day_max": float("nan"),
                "crps_day_mean": float("nan"), "slot_coverage_80": float("nan")}
    return {"days": len(hits), "day_max_coverage_80": round(float(np.mean(hits)), 3),
            "crps_day_max": round(float(np.mean(crps_max)), 5), "crps_day_mean": round(float(np.mean(crps_mean)), 5),
            "slot_coverage_80": round(float(np.mean(slot_cov)), 3)}


BAND = (0.70, 0.90)
TIE = 0.02


def decide(rows: list[dict]) -> dict:
    """Rows ordered simplest first, each with "name" and "protocols" {protocol: evaluate() result}."""
    lo, hi = BAND

    def cov(r):
        return [p["day_max_coverage_80"] for p in r["protocols"].values()]

    def crps(r):
        return float(np.mean([p["crps_day_max"] for p in r["protocols"].values()]))
    in_band = [r for r in rows if all(lo <= c <= hi for c in cov(r))]
    if in_band:
        best = min(crps(r) for r in in_band)
        tied = [r for r in in_band if crps(r) <= best * (1 + TIE)]
        winner = tied[0]
        reason = (f"lowest mean CRPS of the day maximum among candidates inside {lo:.0%}-{hi:.0%} on both protocols; "
                  f"{len(tied)} within {TIE:.0%} of the best, simplest of those wins")
    else:
        winner = min(rows, key=lambda r: max(abs(c - 0.8) for c in cov(r)))
        reason = "no candidate inside the band on both protocols: smallest worst-protocol distance from 80% (a miss)"
    return {"winner": winner["name"], "in_band": [r["name"] for r in in_band], "reason": reason,
            "mean_crps_day_max": {r["name"]: round(crps(r), 5) for r in rows}}


RULE = ("keep candidates with day-maximum 10-90% coverage within 70-90% on both protocols; lowest mean CRPS of the "
        "day maximum wins, candidates within 2% count as tied and the simplest wins; if none is in the band, the "
        "smallest worst-protocol distance from 80% wins and the miss is reported")
SPLIT = "(a) fit Mathura before 2021-01-01, test Mathura 2021; (b) fit all Mathura, test all Bareilly; 200 paths/day, seed 0"


def _series(district: str) -> pd.Series:
    from engine import config
    path = config.PROCESSED_DIR / "v2" / f"upstream_vm_pu_{district}.parquet"
    return pd.read_parquet(path)["upstream_vm_pu"]


def run_bakeoff() -> dict:
    mathura, bareilly = _series("mathura"), _series("bareilly")
    split = pd.Timestamp("2021-01-01")
    rows = []
    for name, cls in CANDIDATES.items():
        rows.append({"name": name, "protocols": {
            "time_mathura_2021": evaluate(cls.fit(mathura[mathura.index < split]), mathura[mathura.index >= split]),
            "district_bareilly": evaluate(cls.fit(mathura), bareilly),
        }})
        print(name, json.dumps(rows[-1]["protocols"]), flush=True)
    return {"candidates": rows, **decide(rows)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bakeoff", action="store_true")
    if ap.parse_args().bakeoff:
        from scripts.bakeoff import record
        result = run_bakeoff()
        print(record("upstream", result, rule=RULE, split=SPLIT))
        print(json.dumps({k: result[k] for k in ("winner", "in_band", "reason")}, indent=2))
        return
    mathura, bareilly = _series("mathura"), _series("bareilly")
    split = pd.Timestamp("2021-01-01")
    out = {"model": UpstreamModel.name,
           "mathura_2021": evaluate(UpstreamModel.fit(mathura[mathura.index < split]), mathura[mathura.index >= split]),
           "bareilly_all_years_with_mathura_model": evaluate(UpstreamModel.fit(mathura), bareilly)}
    path = Path(__file__).resolve().parents[1] / "ml" / "reports" / "upstream_v2.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
