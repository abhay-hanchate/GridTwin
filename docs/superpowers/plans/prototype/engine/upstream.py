"""Day-ahead stochastic model of the voltage arriving at the transformer.

Daily mean = monthly mean + AR(1) deviation (yesterday's mean is known to the operator).
Intra-day = shape by (month, weekend) + AR(1) residual across 15-minute slots.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SLOTS = 96
MIN_VALID_SLOTS = 80
LOW, HIGH = 0.80, 1.20


def _ar1(x: np.ndarray) -> tuple[float, float]:
    """Least-squares AR(1) coefficient and innovation standard deviation."""
    a, b = x[:-1], x[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    phi = float((a * b).sum() / (a * a).sum()) if len(a) > 2 and (a * a).sum() > 0 else 0.0
    phi = float(np.clip(phi, -0.99, 0.99))
    resid = b - phi * a
    return phi, float(resid.std()) if len(resid) > 2 else 0.0


@dataclass
class UpstreamModel:
    month_mean: dict
    phi: float
    sigma_day: float
    shape: dict
    resid_phi: float
    resid_sigma: float
    global_shape: np.ndarray = field(default_factory=lambda: np.zeros(SLOTS))

    @classmethod
    def fit(cls, series: pd.Series) -> "UpstreamModel":
        s = series.asfreq("15min")
        days = {d: g.to_numpy() for d, g in s.groupby(s.index.normalize()) if len(g) == SLOTS}
        valid = {d: v for d, v in days.items() if np.isfinite(v).sum() >= MIN_VALID_SLOTS}
        if len(valid) < 30:
            raise ValueError("need at least 30 usable days to fit the upstream-voltage model")
        day_mean = pd.Series({d: np.nanmean(v) for d, v in valid.items()}).sort_index()
        by_month = day_mean.groupby(day_mean.index.month).mean()
        month_mean = {int(m): float(v) for m, v in by_month.items()}
        dev = pd.Series({d: day_mean[d] - month_mean[d.month] for d in day_mean.index})
        dev = dev.reindex(pd.date_range(dev.index.min(), dev.index.max(), freq="D"))   # gaps stay NaN: pairs are consecutive days
        phi, sigma_day = _ar1(dev.to_numpy())

        shapes: dict = {}
        resid_all = []
        for d, v in valid.items():
            shapes.setdefault((d.month, int(d.dayofweek >= 5)), []).append(v - np.nanmean(v))
        shape = {k: np.nanmean(np.vstack(vs), axis=0) for k, vs in shapes.items()}
        global_shape = np.nanmean(np.vstack([v for vs in shapes.values() for v in vs]), axis=0)
        for d, v in valid.items():
            sh = shape[(d.month, int(d.dayofweek >= 5))]
            resid_all.append(v - np.nanmean(v) - sh)
        resid = np.concatenate([np.r_[r, np.nan] for r in resid_all])
        r_phi, r_sigma = _ar1(resid)
        return cls(month_mean, phi, sigma_day, shape, r_phi, r_sigma, global_shape)

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator, day_z: np.ndarray | None = None) -> np.ndarray:
        """`n` day curves (n, 96). `day_z` (n,) supplies the standard-normal day-level draw when it must be coupled
        to other quantities (the scenario generator's copula); otherwise it is drawn here."""
        date = pd.Timestamp(date)
        prev = date - pd.Timedelta(days=1)
        mu = self.month_mean.get(date.month, float(np.mean(list(self.month_mean.values()))))
        mu_prev = self.month_mean.get(prev.month, mu)
        shock = rng.normal(0, 1, n) if day_z is None else np.asarray(day_z, float)
        day_mean = mu + self.phi * (prev_day_mean - mu_prev) + self.sigma_day * shock
        shape = self.shape.get((date.month, int(date.dayofweek >= 5)), self.global_shape)
        resid = np.zeros((n, SLOTS))
        var0 = self.resid_sigma ** 2 / max(1e-9, 1 - self.resid_phi ** 2)
        resid[:, 0] = rng.normal(0, np.sqrt(var0), n)
        for t in range(1, SLOTS):
            resid[:, t] = self.resid_phi * resid[:, t - 1] + rng.normal(0, self.resid_sigma, n)
        return np.clip(day_mean[:, None] + shape[None, :] + resid, LOW, HIGH)


def evaluate(model: UpstreamModel, series: pd.Series, n: int = 200, seed: int = 0) -> dict:
    """Coverage of the 10-90% interval of the daily maximum, given only yesterday's observed mean."""
    s = series.asfreq("15min")
    rng = np.random.default_rng(seed)
    hits, days = 0, 0
    prev_mean = None
    for d, g in s.groupby(s.index.normalize()):
        v = g.to_numpy()
        if len(v) != SLOTS or np.isfinite(v).sum() < MIN_VALID_SLOTS:
            prev_mean = None
            continue
        today_mean = float(np.nanmean(v))
        if prev_mean is not None:
            peak = model.sample(d, n, prev_mean, rng).max(axis=1)
            lo, hi = np.quantile(peak, [0.1, 0.9])
            hits += int(lo <= np.nanmax(v) <= hi)
            days += 1
        prev_mean = today_mean
    return {"days": days, "day_max_coverage_80": round(hits / days, 3) if days else float("nan")}


def main() -> None:
    from engine import config
    out = {}
    base = config.PROCESSED_DIR / "v2"
    train = pd.read_parquet(base / "upstream_vm_pu_mathura.parquet")["upstream_vm_pu"]
    model = UpstreamModel.fit(train[train.index < "2021-01-01"])
    out["mathura_2021"] = evaluate(model, train[train.index >= "2021-01-01"])
    bar = pd.read_parquet(base / "upstream_vm_pu_bareilly.parquet")["upstream_vm_pu"]
    out["bareilly_all_years_with_mathura_model"] = evaluate(model, bar)
    path = Path(__file__).resolve().parents[1] / "ml" / "reports" / "upstream_v2.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
