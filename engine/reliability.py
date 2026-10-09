"""D1: does "P(unsafe) = 60% at 12:30" mean that 60% of such moments really were unsafe? A reliability backtest.

No forecast archive overlaps the CEEW meter years, so the backtest cannot use real forecasts. Instead, for every held-out
day it gives the generator only COARSE knowledge that a forecast would carry: the weather class of the day (cloudy,
mixed, sunny), the month, the day type and yesterday's mean grid voltage. It then predicts P(unsafe) per step and
compares it with the replay of what that day actually did (observed demand, observed voltage, ERA5-driven PV).
The result is an upper bound on risk-model skill with coarse knowledge, not a claim about live forecast skill;
solar forecast calibration is reported separately (ml.solar_v2, 2025).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.risk import assess_risk
from engine.rules import VoltageRule
from engine.scenario_gen import SLOTS, AnalogPool, ScenarioGenerator, day_table, fit_copula
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch, Network
from engine.upstream import UpstreamModel
from engine.violations import evaluate

CLASSES = ("cloudy", "mixed", "sunny")
BINS = np.linspace(0, 1, 6)                      # five reliability bins: 0-0.2 ... 0.8-1.0


@dataclass
class Climatology:
    """P10/P50/P90 curves per (weather class, month) for solar and per (weekend, month) for demand, from training days."""
    thresholds: tuple[float, float]
    solar: dict
    demand: dict

    @staticmethod
    def weather_class(clearness: float, thresholds: tuple[float, float]) -> str:
        return CLASSES[int(clearness >= thresholds[0]) + int(clearness >= thresholds[1])]

    @classmethod
    def build(cls, table: pd.DataFrame, pv: pd.Series, load_kw: pd.DataFrame) -> "Climatology":
        thresholds = tuple(float(x) for x in table["clearness"].quantile([1 / 3, 2 / 3]))
        street = load_kw.mean(axis=1)
        solar_days, demand_days = {}, {}
        for d in table.index:
            pv_day, dem_day = pv.loc[d:d + pd.Timedelta(hours=23, minutes=45)], street.loc[d:d + pd.Timedelta(hours=23, minutes=45)]
            if len(pv_day) != SLOTS or len(dem_day) != SLOTS or dem_day.isna().any():
                continue
            solar_days.setdefault((cls.weather_class(table.loc[d, "clearness"], thresholds), d.month), []).append(pv_day.to_numpy(float))
            demand_days.setdefault((int(d.dayofweek >= 5), d.month), []).append(dem_day.to_numpy(float))

        def quantiles(days):
            a = np.vstack(days)
            return pd.DataFrame(np.quantile(a, [0.1, 0.5, 0.9], axis=0).T, columns=["p10", "p50", "p90"])
        return cls(thresholds, {k: quantiles(v) for k, v in solar_days.items() if len(v) >= 3},
                   {k: quantiles(v) for k, v in demand_days.items() if len(v) >= 3})

    def _nearest(self, table: dict, key: tuple) -> pd.DataFrame:
        if key in table:
            return table[key]
        same = [k for k in table if k[0] == key[0]] or list(table)
        return table[min(same, key=lambda k: min((k[1] - key[1]) % 12, (key[1] - k[1]) % 12))]

    def solar_forecast(self, weather_class: str, month: int) -> pd.DataFrame:
        return self._nearest(self.solar, (weather_class, month))

    def demand_forecast(self, weekend: int, month: int) -> pd.DataFrame:
        return self._nearest(self.demand, (weekend, month))


def actual_scenario(date: pd.Timestamp, load_kw: pd.DataFrame, pv: pd.Series, upstream: pd.Series, n_homes: int,
                    seed: int = 42) -> DayScenarioBatch:
    """What the day really did, on the same street: meters assigned to homes with a seeded draw."""
    day = slice(date, date + pd.Timedelta(hours=23, minutes=45))
    loads = load_kw.loc[day]
    loads = loads.loc[:, loads.notna().all()]
    cols = np.random.default_rng(seed).choice(np.asarray(loads.columns), n_homes)
    return DayScenarioBatch(t=loads.index, load_kw=loads[cols].to_numpy(float)[None], pv_per_kwp=pv.loc[day].to_numpy(float)[None],
                            upstream_pu=upstream.loc[day].to_numpy(float)[None], load_pf=0.95, labels=(str(date.date()),))


def reliability_table(pred: np.ndarray, observed: np.ndarray) -> list[dict]:
    """Mean predicted probability against observed frequency in five bins."""
    p, o = pred.ravel(), observed.ravel().astype(float)
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                     "mean_predicted": round(float(p[m].mean()), 3) if m.any() else None,
                     "observed_frequency": round(float(o[m].mean()), 3) if m.any() else None})
    return rows


def brier(pred: np.ndarray, observed: np.ndarray) -> float:
    return float(np.mean((pred - observed.astype(float)) ** 2))


def backtest(network: Network, rule: VoltageRule, load_kw: pd.DataFrame, pv: pd.Series, upstream: pd.Series, *,
             split: str, n_days: int = 40, n_scenarios: int = 30, seed: int = 42, controls: Controls = Controls(),
             test_end: str | None = None, return_pairs: bool = False) -> dict:
    """Fit everything on days before `split`, then predict and replay `n_days` evenly spaced days from `split` (up to
    `test_end` when given). `return_pairs` adds the raw (predicted, observed) step arrays for recalibration."""
    train_loads, train_up = load_kw[load_kw.index < split], upstream[upstream.index < split]
    table = day_table(train_loads, pv[pv.index < split], train_up)
    full = day_table(load_kw, pv, upstream)
    clim = Climatology.build(table, pv, load_kw)
    gen = ScenarioGenerator(fit_copula(table), UpstreamModel.fit(train_up), AnalogPool.build(train_loads))
    solver = DaySolver(network, asymmetric=True)
    rng = np.random.default_rng(seed)

    def usable(d: pd.Timestamp) -> bool:
        day, prev = slice(d, d + pd.Timedelta(hours=23, minutes=45)), slice(d - pd.Timedelta(days=1), d - pd.Timedelta(minutes=15))
        loads = load_kw.loc[day]
        return (len(loads) == SLOTS and int(loads.notna().all().sum()) >= 5 and len(pv.loc[day]) == SLOTS
                and upstream.loc[day].notna().sum() == SLOTS and upstream.loc[prev].notna().sum() == SLOTS)

    end = pd.Timestamp(test_end) if test_end else pd.Timestamp.max
    test_days = [d for d in full.index if pd.Timestamp(split) <= d < end and usable(d)]
    chosen = [test_days[i] for i in np.linspace(0, len(test_days) - 1, min(n_days, len(test_days))).astype(int)]
    predicted, observed, hours_pred, hours_obs = [], [], [], []
    for d in chosen:
        cls = Climatology.weather_class(float(full.loc[d, "clearness"]), clim.thresholds)
        prev_mean = float(upstream.loc[d - pd.Timedelta(days=1):d - pd.Timedelta(minutes=15)].mean())
        scn = gen.sample(d, n_scenarios, clim.solar_forecast(cls, d.month), clim.demand_forecast(int(d.dayofweek >= 5), d.month),
                         prev_mean, network.n_homes, rng)
        risk = assess_risk(solver, scn, controls, rule)
        actual = evaluate(solver.solve(actual_scenario(d, load_kw, pv, upstream, network.n_homes), controls), rule)
        predicted.append(risk.p_unsafe)
        observed.append(actual.unsafe[0])
        hours_pred.append(risk.expected_unsafe_hours)
        hours_obs.append(float(actual.unsafe[0].sum() * 0.25))
    pred, obs = np.array(predicted), np.array(observed)
    base_rate = float(obs.mean())
    b, b_ref = brier(pred, obs), brier(np.full_like(pred, base_rate), obs)
    out = {
        "days": len(chosen), "scenarios_per_day": n_scenarios, "split": split, "rule": rule.id,
        "observed_unsafe_share_of_steps": round(base_rate, 4),
        "brier": round(b, 4), "brier_climatology": round(b_ref, 4),
        "brier_skill": round(1 - b / b_ref, 3) if b_ref > 0 else None,
        "reliability": reliability_table(pred, obs),
        "unsafe_hours": {"predicted_mean": round(float(np.mean(hours_pred)), 2), "observed_mean": round(float(np.mean(hours_obs)), 2),
                         "correlation": round(float(np.corrcoef(hours_pred, hours_obs)[0, 1]), 3) if np.std(hours_obs) > 0 and np.std(hours_pred) > 0 else None},
        "limitation": "Generator conditioned on coarse weather class, month, day type and yesterday's voltage; not live forecasts.",
    }
    if return_pairs:
        out["pairs"] = {"predicted": pred, "observed": obs}
    return out
