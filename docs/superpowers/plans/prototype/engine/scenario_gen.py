"""B5: joint scenarios for tomorrow from three marginal forecasts and a day-level correlation.

Solar (clearness), demand (level) and the upstream voltage (day offset) are not independent: sunny days differ from
cloudy ones in grid voltage, and heavy-demand days pull the voltage down. A Gaussian copula on the day-level rank-normal
scores of those three anomalies (estimated from the CEEW years) couples the draws. Within a day the solar error is a
mix of the shared day-level draw and an AR(1) wobble, because cloud errors persist but not perfectly.

Stated limitation: the copula models CLIMATOLOGICAL anomalies of the observed years. Forecast archives do not overlap
the meter years, so forecast-error correlation cannot be estimated. The Proof page says so.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from engine.types import DayScenarioBatch
from engine.upstream import UpstreamModel

SLOTS = 96
Z10 = float(stats.norm.ppf(0.9))                 # 1.2816: the P90 level in standard-normal units
ANOMALIES = ("clearness", "demand_index", "upstream_offset")
MIN_METERS = 5
MIN_SLOTS = 80
RATIO_FLOOR_KW = 0.05
RATIO_CAP = 8.0


def day_table(load_kw: pd.DataFrame, pv_kw_per_kwp: pd.Series, upstream_pu: pd.Series) -> pd.DataFrame:
    """One row per day with the three anomalies.

    clearness      daily PV energy over the 90th percentile of the surrounding 31 days (a robust clear-day reference)
    demand_index   daily mean demand over the 31-day rolling median
    upstream_offset daily mean upstream voltage minus its calendar-month mean
    """
    street = load_kw.mean(axis=1).where(load_kw.notna().sum(axis=1) >= MIN_METERS)
    pv_daily = pv_kw_per_kwp.resample("D").sum()
    table = pd.DataFrame({"demand": street.resample("D").mean(), "up": upstream_pu.resample("D").mean(),
                          "slots": street.resample("D").count()})
    table = table[table["slots"] >= MIN_SLOTS].dropna()
    ref = pv_daily.rolling(31, center=True, min_periods=10).quantile(0.9)
    table["clearness"] = (pv_daily / ref).reindex(table.index)
    table["demand_index"] = table["demand"] / table["demand"].rolling(31, center=True, min_periods=10).median()
    table["upstream_offset"] = table["up"] - table["up"].groupby(table.index.month).transform("mean")
    return table[list(ANOMALIES)].dropna()


def fit_copula(table: pd.DataFrame) -> np.ndarray:
    """3x3 correlation of the rank-normal scores, in the order of ANOMALIES."""
    if len(table) < 60:
        raise ValueError("need at least 60 days to estimate the day-level correlation")
    z = table[list(ANOMALIES)].rank().sub(0.5).div(len(table)).apply(stats.norm.ppf)
    return z.corr().to_numpy()


def quantile_path(fc: pd.DataFrame, z: np.ndarray) -> np.ndarray:
    """Forecast value at standard-normal level `z` (per scenario and step) from the P10/P50/P90 columns.

    Piecewise linear through (-1.28, p10), (0, p50), (+1.28, p90) and extended linearly beyond, never below zero.
    `fc` has T rows; `z` is (S,) or (S, T). Returns (S, T).
    """
    p10, p50, p90 = (fc[c].to_numpy(float)[None, :] for c in ("p10", "p50", "p90"))
    z = np.asarray(z, float)
    z = z[:, None] if z.ndim == 1 else z
    lower = p50 + (z / Z10) * (p50 - p10)
    upper = p50 + (z / Z10) * (p90 - p50)
    return np.clip(np.where(z < 0, lower, upper), 0.0, None)


@dataclass
class AnalogPool:
    """Observed full days of per-meter demand, grouped by (month, weekend)."""
    days: dict            # (month, weekend) -> list of (96, meters) arrays, meters with complete data that day
    mean_by_day: dict     # same keys -> list of (96,) street means

    @classmethod
    def build(cls, load_kw: pd.DataFrame) -> "AnalogPool":
        days, means = {}, {}
        for d, g in load_kw.groupby(load_kw.index.normalize()):
            if len(g) != SLOTS:
                continue
            full = g.loc[:, g.notna().all()]
            if full.shape[1] < MIN_METERS:
                continue
            key = (d.month, int(d.dayofweek >= 5))
            days.setdefault(key, []).append(full.to_numpy(float))
            means.setdefault(key, []).append(full.to_numpy(float).mean(axis=1))
        if not days:
            raise ValueError("no complete day with enough meters")
        return cls(days, means)

    def _key(self, date: pd.Timestamp) -> tuple:
        key = (date.month, int(date.dayofweek >= 5))
        if key in self.days:
            return key
        same_type = [k for k in self.days if k[1] == key[1]] or list(self.days)
        return min(same_type, key=lambda k: min((k[0] - key[0]) % 12, (key[0] - k[0]) % 12))

    def home_ratios(self, date, n_scn: int, n_homes: int, rng: np.random.Generator) -> np.ndarray:
        """(S, T, H) demand of each home relative to its day's street mean, from random analog days and meters."""
        key = self._key(pd.Timestamp(date))
        pool, means = self.days[key], self.mean_by_day[key]
        out = np.empty((n_scn, SLOTS, n_homes))
        for s in range(n_scn):
            i = int(rng.integers(len(pool)))
            cols = rng.integers(pool[i].shape[1], size=n_homes)
            out[s] = np.clip(pool[i][:, cols] / np.maximum(means[i], RATIO_FLOOR_KW)[:, None], 0, RATIO_CAP)
        return out


@dataclass
class ScenarioGenerator:
    corr: np.ndarray                # (3, 3) copula correlation in the order of ANOMALIES
    upstream: UpstreamModel
    analogs: AnalogPool
    day_share: float = 0.7          # share of the solar error variance that is shared across the whole day
    intraday_phi: float = 0.9       # AR(1) persistence of the remaining, hour-to-hour part

    def sample(self, date, n: int, solar_fc: pd.DataFrame, demand_fc: pd.DataFrame, prev_day_upstream_mean: float,
               n_homes: int, rng: np.random.Generator, temperature_c: np.ndarray | None = None, load_pf: float = 0.95) -> DayScenarioBatch:
        """`n` correlated scenarios for `date`. Both forecasts are 96-row frames with p10, p50, p90."""
        if len(solar_fc) != SLOTS or len(demand_fc) != SLOTS:
            raise ValueError("forecasts must have 96 quarter-hour rows")
        date = pd.Timestamp(date)
        z = rng.multivariate_normal(np.zeros(3), self.corr, size=n)                   # (n, 3): clearness, demand, upstream
        # Sun: shared day-level error plus an AR(1) wobble; the marginal at each step stays standard normal.
        eps = rng.normal(size=(n, SLOTS))
        wobble = np.empty_like(eps)
        wobble[:, 0] = eps[:, 0]
        for t in range(1, SLOTS):
            wobble[:, t] = self.intraday_phi * wobble[:, t - 1] + np.sqrt(1 - self.intraday_phi ** 2) * eps[:, t]
        z_solar = np.sqrt(self.day_share) * z[:, [0]] + np.sqrt(1 - self.day_share) * wobble
        pv = quantile_path(solar_fc, z_solar)
        demand_mean = quantile_path(demand_fc, z[:, 1])                                # (n, T)
        ratios = self.analogs.home_ratios(date, n, n_homes, rng)                       # (n, T, H)
        load = demand_mean[:, :, None] * ratios
        upstream = self.upstream.sample(date, n, prev_day_upstream_mean, rng, day_z=z[:, 2])
        ambient = None if temperature_c is None else np.tile(np.asarray(temperature_c, float), (n, 1))
        return DayScenarioBatch(t=pd.date_range(date, periods=SLOTS, freq="15min"), load_kw=load, pv_per_kwp=pv,
                                upstream_pu=upstream, load_pf=load_pf, labels=tuple(f"{date.date()}#{i}" for i in range(n)),
                                ambient_c=ambient)
