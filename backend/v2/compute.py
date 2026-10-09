"""Heavy computations behind /risk, /fixes and /simulate, returning the shapes in frontend/src/api/v2types.ts.

Inputs for a demo date ("tomorrow" in 2025):
  solar        solar v2 day-ahead forecast (P10/P50/P90), hourly, interpolated to 15 minutes      modeled
  demand       per-(weekend, month) climatology of the 2019-2021 CEEW meters, analog-day homes     modeled
  grid voltage upstream model fitted on CEEW; yesterday's mean from the same calendar day of 2019 modeled (proxy)
Scenarios are drawn by the copula generator (engine.scenario_gen) with a fixed seed, so reruns agree.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from backend.v2.errors import ApiError
from engine import config
from engine.archetypes import ARCHETYPES, build
from engine.fixes import tournament
from engine.fixes.battery import solve_with_battery
from engine.fixes.base import margin_v
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.reliability import Climatology
from engine.risk import assess_risk
from engine.rules import get_rule
from engine.scenario_gen import AnalogPool, ScenarioGenerator, day_table, fit_copula
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.upstream import UpstreamModel
from engine.violations import evaluate, summarise

N_SCENARIOS = 100
SEED = 42
NOMINAL_V = 230.0
PROXY_YEAR = 2019
PHASE = ("A", "B", "C")
WINDOW_KEYS = {"15 min": "15min", "1 h": "1h", "3 h": "3h", "24 h": "24h"}
SHARE_KEYS = {"over": "overvoltage", "under": "undervoltage", "line": "line_overload", "trafo": "trafo_overload",
              "solver": "solver_failure"}
PROVENANCE = {"solar": "modeled: solar v2 day-ahead forecast (five weather models, LightGBM, conformal)",
              "demand": "modeled: CEEW 2019-2021 climatology by month and day type; homes from analog days",
              "voltage": "modeled: upstream-voltage model; yesterday's mean from the same date of 2019 (proxy)",
              "grid": "benchmark: SimBench topology with IS 398 conductors; homes on single phases"}

_VV, _VW = VoltVarCurve(), VoltWattCurve()
SIMPLE_FIXES = {
    "none": Controls(),
    "tap_plus1": Controls(tap_pos=1), "tap_plus2": Controls(tap_pos=2),
    "volt_var": Controls(volt_var=_VV), "volt_watt": Controls(volt_watt=_VW),
    "volt_var_watt": Controls(volt_var=_VV, volt_watt=_VW),
    "tap1_volt_var": Controls(tap_pos=1, volt_var=_VV), "tap2_volt_var": Controls(tap_pos=2, volt_var=_VV),
    "tap1_volt_var_watt": Controls(tap_pos=1, volt_var=_VV, volt_watt=_VW),
    "export_cap_80": Controls(curtail_keep=0.8), "export_cap_60": Controls(curtail_keep=0.6),
}


# ---- inputs ----------------------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _history():
    base = config.PROCESSED_DIR
    load = pd.read_parquet(base / "load_kw.parquet")
    pv = pd.read_parquet(base / "pv_kw_per_kwp.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / "upstream_vm_pu.parquet")["upstream_vm_pu"]
    table = day_table(load, pv, up)
    generator = ScenarioGenerator(fit_copula(table), UpstreamModel.fit(up), AnalogPool.build(load))
    return generator, Climatology.build(table, pv, load), up


@lru_cache(maxsize=1)
def _solar_table() -> pd.DataFrame:
    return pd.read_parquet(config.PROCESSED_DIR / "solar_forecast_v2_2025.parquet")


def solar_forecast(date: str) -> pd.DataFrame:
    """96 quarter-hour P10/P50/P90 rows in kW per installed kW for `date` (zero at night)."""
    fc = _solar_table()
    day = fc[fc.index.normalize() == pd.Timestamp(date)]
    if day.empty:
        lo, hi = fc.index.min().date(), fc.index.max().date()
        raise ApiError(404, f"no solar forecast for {date}; available {lo} to {hi}")
    start = pd.Timestamp(date)
    hourly = day[["p10", "p50", "p90"]].reindex(pd.date_range(start, periods=25, freq="h"), fill_value=0.0)
    quarter = hourly.resample("15min").interpolate("time").iloc[:96]
    return quarter.clip(lower=0).reset_index(drop=True)


def yesterday_upstream_mean(date: pd.Timestamp, up: pd.Series) -> float:
    proxy = pd.Timestamp(PROXY_YEAR, date.month, date.day) - pd.Timedelta(days=1)
    window = up.loc[proxy:proxy + pd.Timedelta(hours=23, minutes=45)]
    if window.notna().sum() >= 80:
        return float(window.mean())
    same_month = up[up.index.month == date.month]
    return float(same_month.mean() if len(same_month) else up.mean())


def check_network(network_id: str) -> str:
    """Validate the id without building the network (building loads SimBench, about 3 s)."""
    if network_id not in ARCHETYPES:
        raise ApiError(404, f"unknown network {network_id!r}", details={"valid": sorted(ARCHETYPES)})
    return network_id


@lru_cache(maxsize=8)
def network(network_id: str):
    return build(check_network(network_id), phases="round_robin")


def rule(rule_id: str):
    try:
        return get_rule(rule_id)
    except KeyError as exc:
        raise ApiError(404, str(exc).strip("'\"")) from exc


def scenarios(date: str, net, n: int = N_SCENARIOS, seed: int = SEED) -> DayScenarioBatch:
    generator, clim, up = _history()
    d = pd.Timestamp(date)
    demand = clim.demand_forecast(int(d.dayofweek >= 5), d.month)
    return generator.sample(d, n, solar_forecast(date), demand, yesterday_upstream_mean(d, up), net.n_homes,
                            np.random.default_rng(seed))


def _labels(t: pd.DatetimeIndex) -> list[str]:
    return [x.strftime("%H:%M") for x in t]


def _controls(fix: str | None) -> Controls:
    if fix is None:
        return Controls()
    if fix not in SIMPLE_FIXES:
        raise ApiError(404, f"unknown fix {fix!r} for risk replays", details={"valid": sorted(SIMPLE_FIXES)})
    return SIMPLE_FIXES[fix]


# ---- /risk -----------------------------------------------------------------------------------------------------

def risk_payload(date: str, network_id: str, rule_id: str, fix: str | None = None, *, n: int = N_SCENARIOS,
                 watch: float = 0.20, act: float = 0.50) -> dict:
    net, r = network(network_id), rule(rule_id)
    scn = scenarios(date, net, n)
    res = assess_risk(DaySolver(net, asymmetric=True), scn, _controls(fix), r, watch=watch, act=act)
    p = [round(float(x), 3) for x in res.p_unsafe]
    return {
        "date": date, "network": network_id, "rule": r.id, "fix": fix or "none", "level": res.level,
        "p_unsafe": p, "t": _labels(res.t), "thresholds": {"watch": watch, "act": act},
        "expected_unsafe_hours": {"mean": round(res.expected_unsafe_hours, 2), "p10": round(res.unsafe_hours_p10, 2),
                                  "p90": round(res.unsafe_hours_p90, 2)},
        "first_watch": res.first_watch, "first_act": res.first_act,
        "peak_voltage_v": {k: round(v, 1) for k, v in res.peak_voltage_v.items()},
        "window_risk": {WINDOW_KEYS[k]: round(v, 3) for k, v in res.window_risk.items()},
        "shares": {SHARE_KEYS[k]: round(v, 3) for k, v in res.shares.items()},
        "n_scenarios": res.n_scenarios, "provenance": PROVENANCE,
        "calibration": calibration(r.id, p),
    }


def calibration(rule_id: str, raw: list[float]) -> dict:
    """Isotonic map from scripts.calibrate_risk when it exists; `reliable` only if it beat the base rate held out."""
    path = config.ROOT / "data" / "results" / f"risk_calibration_{rule_id}.json"
    try:
        cal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"reliable": False, "raw": raw, "calibrated": raw, "method": "none (gate G8 not met)"}
    mapped = np.interp(raw, cal["map"]["x"], cal["map"]["y"])
    return {"reliable": bool(cal["reliable"]), "raw": raw, "calibrated": [round(float(x), 3) for x in mapped],
            "method": "isotonic, fitted on 2020-05..12, tested on held-out 2021",
            "held_out_skill": cal["held_out_test"]["skill_calibrated"]}


# ---- /fixes ----------------------------------------------------------------------------------------------------

def robust_set(scn: DayScenarioBatch) -> DayScenarioBatch:
    """Median sun, P90 grid voltage and P90 sun (last: the design case the plans are built on)."""
    energy, volts = scn.pv_per_kwp.sum(axis=1), scn.upstream_pu.mean(axis=1)
    pick = lambda values, q: int(np.argmin(np.abs(values - np.quantile(values, q))))  # noqa: E731
    idx = list(dict.fromkeys([pick(energy, 0.5), pick(volts, 0.9), pick(energy, 0.9)]))
    return DayScenarioBatch(scn.t, scn.load_kw[idx], scn.pv_per_kwp[idx], scn.upstream_pu[idx], scn.load_pf,
                            tuple(scn.labels[i] for i in idx))


def _design(scn: DayScenarioBatch) -> DayScenarioBatch:
    return DayScenarioBatch(scn.t, scn.load_kw[-1:], scn.pv_per_kwp[-1:], scn.upstream_pu[-1:], scn.load_pf, scn.labels[-1:])


def _solve(candidate, scn, r):
    if candidate.battery is not None:
        return solve_with_battery(candidate.network, scn, candidate.battery, r, candidate.controls)
    return DaySolver(candidate.network, asymmetric=True).solve(scn, candidate.controls)


def _peak_v(res) -> list[float]:
    return [round(float(v) * NOMINAL_V, 1) for v in np.nanmax(res.u_pu[0], axis=(1, 2))]


def details(candidate, base_net, scn, r, before) -> dict:
    design = _design(scn)
    out = {"voltage": {"t": _labels(scn.t), "before_max_v": _peak_v(before), "after_max_v": _peak_v(_solve(candidate, design, r))}}
    moved = np.flatnonzero(candidate.network.house_phase != base_net.house_phase) \
        if len(candidate.network.house_phase) == len(base_net.house_phase) else np.array([], dtype=int)
    if len(moved):
        out["phase_moves"] = [{"home": int(h), "from": PHASE[base_net.house_phase[h]], "to": PHASE[candidate.network.house_phase[h]]}
                              for h in moved]
    lim = candidate.controls.export_limit_kw
    if lim is not None:
        lim = np.broadcast_to(np.asarray(lim, float), (len(scn.t), base_net.n_homes))
        binding = np.flatnonzero((lim < base_net.house_kwp[None, :] - 1e-6).any(axis=0))
        out["export_limits"] = {"homes": [int(h) for h in binding], "t": _labels(scn.t),
                                "kw": [[round(float(x), 2) for x in lim[:, h]] for h in binding]}
    return out


def fixes_payload(date: str, network_id: str, rule_id: str, *, n: int = N_SCENARIOS, include_battery: bool = True,
                  include_switching: bool = True) -> dict:
    net, r = network(network_id), rule(rule_id)
    scn = robust_set(scenarios(date, net, n))
    result = tournament.run(net, scn, r, include_battery=include_battery, include_switching=include_switching)
    before = DaySolver(net, asymmetric=True).solve(_design(scn))
    focus = result.verdict["recommended"] or result.verdict["closest"]
    outcomes = []
    for o in result.outcomes:
        c = o.candidate
        row = {"id": c.id, "label": c.label, "kind": c.kind, "safe": o.acceptable, "unsafe_steps": o.unsafe_steps,
               "rank": o.rank, "binding_limit": o.binding_limit,
               "cost": {"curtailed_kwh": o.summary["curtailed_kwh"], "operations": c.operations,
                        "battery_throughput_kwh": o.summary["battery_throughput_kwh"],
                        "margin_v": round(margin_v(o.summary, r), 1)}}
        if c.id == focus:
            row["details"] = details(c, net, scn, r, before)
        outcomes.append(row)
    return {"date": date, "network": network_id, "rule": r.id, "baseline_unsafe_steps": result.verdict["baseline_unsafe_steps"],
            "verdict": result.verdict, "outcomes": outcomes, "n_scenarios": result.n_scenarios,
            "scenarios": list(scn.labels), "provenance": PROVENANCE}


# ---- /simulate -------------------------------------------------------------------------------------------------

def simulate_payload(date: str, network_id: str, rule_id: str, fix: str = "none", *, n: int = N_SCENARIOS) -> dict:
    """The design-case day (P90 sun) without and with one fix, step by step."""
    net, r = network(network_id), rule(rule_id)
    design = _design(robust_set(scenarios(date, net, n)))
    solver = DaySolver(net, asymmetric=True)
    runs = {"before": solver.solve(design), "after": solver.solve(design, _controls(fix))}
    out = {"date": date, "network": network_id, "rule": r.id, "fix": fix, "t": _labels(design.t),
           "limits_v": {"min": r.vmin_v, "max": r.vmax_v}, "provenance": PROVENANCE}
    for key, res in runs.items():
        v = evaluate(res, r)
        out[key] = {"max_v": _peak_v(res), "min_v": [round(float(x) * NOMINAL_V, 1) for x in np.nanmin(res.u_pu[0], axis=(1, 2))],
                    "unsafe": [bool(x) for x in v.unsafe[0]], "summary": summarise(res, v)}
    return out



# ---- planning (/headroom, /connection-check) -------------------------------------------------------------------

DEFAULT_ADOPTION = 0.3


def planning_street(date: str, network_id: str, adoption: float = DEFAULT_ADOPTION):
    """The street with `adoption` of its homes on solar (spread evenly along it) and the design-case day."""
    net = network(network_id)
    chosen = np.zeros(net.n_homes, dtype=bool)
    chosen[np.round(np.linspace(0, net.n_homes - 1, int(round(adoption * net.n_homes)))).astype(int)] = True
    net = net.with_pv(net.house_kwp * chosen)
    return net, _design(robust_set(scenarios(date, net)))


def headroom_payload(date: str, network_id: str, rule_id: str, adoption: float = DEFAULT_ADOPTION) -> dict:
    from engine.headroom import headroom
    net, design = planning_street(date, network_id, adoption)
    out = headroom(net, design, rule(rule_id))
    return {"date": date, "network": network_id, "adoption": adoption, **out, "provenance": PROVENANCE}


def connection_payload(date: str, network_id: str, rule_id: str, node: int, kw: float, count: int,
                       phase: str | None, adoption: float = DEFAULT_ADOPTION) -> dict:
    from engine.headroom import check_connection
    net, design = planning_street(date, network_id, adoption)
    try:
        out = check_connection(net, design, rule(rule_id), node=node, kw=kw, count=count,
                               phase=None if phase is None else PHASE.index(phase))
    except ValueError as exc:
        raise ApiError(422, str(exc), details={"valid_nodes": [int(n) for n in net.lv_nodes]}) from exc
    return {"date": date, "network": network_id, "adoption": adoption, **out, "provenance": PROVENANCE}


def hosting_payload(date: str, network_id: str, rule_id: str, draws: int = 30) -> dict:
    """P10/P50/P90 hosting capacity on the design-case day, without a fix and with standard Volt/VAR."""
    from engine.hosting import hosting_capacity
    net = network(network_id)
    design = _design(robust_set(scenarios(date, net)))
    r = rule(rule_id)
    return {"date": date, "network": network_id, "rule": r.id,
            "without_fix": hosting_capacity(net, design, r, draws=draws),
            "with_volt_var": hosting_capacity(net, design, r, draws=draws, controls=Controls(volt_var=_VV)),
            "provenance": PROVENANCE}
