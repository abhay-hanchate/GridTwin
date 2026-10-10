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
PROXY_YEARS = (2019, 2020, 2021)            # which year's "yesterday" stands in for a 2025 date, first with data
PHASE = ("A", "B", "C")
WINDOW_KEYS = {"15 min": "15min", "1 h": "1h", "3 h": "3h", "24 h": "24h"}
SHARE_KEYS = {"over": "overvoltage", "under": "undervoltage", "line": "line_overload", "trafo": "trafo_overload",
              "solver": "solver_failure"}
PROVENANCE = {"solar": "modeled: solar v2 day-ahead forecast (five weather models, LightGBM, conformal)",
              "demand": "modeled: CEEW 2019-2021 climatology by month and day type; homes from analog days",
              "voltage": "modeled: upstream-voltage model; yesterday's mean from the same date of an earlier year (proxy)",
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

def _history_files() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    """Mathura's demand, solar and grid voltage for the scenario generator.

    The full record (May 2019 to February 2021, every month of the year) when `data/processed/v2` has it. The older
    committed files miss March and April and most of 2020, which left those months with no voltage history; they are
    only a fallback for a checkout that does not have the full files."""
    v2, base = config.PROCESSED_DIR / "v2", config.PROCESSED_DIR
    names = ("load_kw_mathura", "pv_kw_per_kwp_mathura", "upstream_vm_pu_mathura")
    if all((v2 / f"{n}.parquet").is_file() for n in names):
        return (pd.read_parquet(v2 / f"{names[0]}.parquet"), pd.read_parquet(v2 / f"{names[1]}.parquet")["pv_kw_per_kwp"],
                pd.read_parquet(v2 / f"{names[2]}.parquet")["upstream_vm_pu"], "full")
    return (pd.read_parquet(base / "load_kw.parquet"), pd.read_parquet(base / "pv_kw_per_kwp.parquet")["pv_kw_per_kwp"],
            pd.read_parquet(base / "upstream_vm_pu.parquet")["upstream_vm_pu"], "legacy")


@lru_cache(maxsize=1)
def _history():
    load, pv, up, _ = _history_files()
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
    """Mean grid voltage (pu) of the day before `date` in an earlier year: the same calendar day of 2019, else of 2020
    or 2021, whichever has the record (the data runs May 2019 to February 2021, so Januarys and Februarys come from
    2020 and 2021 and March and April from 2020). Failing that, the mean of that month in the record, then of all of it.
    Never NaN: a missing value would reach the voltage model silently."""
    for year in PROXY_YEARS:
        try:
            proxy = pd.Timestamp(year, date.month, date.day) - pd.Timedelta(days=1)
        except ValueError:                                         # 29 February in a non-leap year
            continue
        window = up.loc[proxy:proxy + pd.Timedelta(hours=23, minutes=45)]
        if window.notna().sum() >= 80:
            return float(window.mean())
    month = up[up.index.month == date.month].dropna()
    return float(month.mean() if len(month) else up.mean())


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


@lru_cache(maxsize=4)
def _live(date: str) -> dict:
    from backend.v2.live_inputs import live_forecasts
    return live_forecasts(date)


def provenance(date: str) -> dict:
    """Where the inputs for `date` come from: Person B's live forecasts for today and later, demo inputs before."""
    from backend.v2.live_inputs import is_live
    return {**PROVENANCE, **_live(date)["provenance"]} if is_live(date) else PROVENANCE


def scenarios(date: str, net, n: int = N_SCENARIOS, seed: int = SEED) -> DayScenarioBatch:
    from backend.v2.live_inputs import is_live
    generator, clim, up = _history()
    d = pd.Timestamp(date)
    if is_live(date):
        f = _live(date)
        return generator.sample(d, n, f["solar"], f["demand"], 1.0, net.n_homes, np.random.default_rng(seed),
                                upstream_fc=f["voltage_pu"])
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
    solver, controls = DaySolver(net, asymmetric=True), _controls(fix)
    res = assess_risk(solver, scn, controls, r, watch=watch, act=act)
    p = [round(float(x), 3) for x in res.p_unsafe]
    # The same scenarios with every panel off: what stays unsafe is the grid's own voltage (or demand), not solar.
    dark = DayScenarioBatch(scn.t, scn.load_kw, np.zeros_like(scn.pv_per_kwp), scn.upstream_pu, scn.load_pf, scn.labels)
    p_dark = [round(float(x), 3) for x in evaluate(solver.solve(dark, controls), r).unsafe.mean(axis=0)]
    labels = _labels(res.t)
    cal = calibration(r.id, p)
    # The map was fitted with no fix on the benchmark street; anywhere else it would be an extrapolation.
    shown = shown_series(cal, p, p_dark, labels, applies=fix in (None, "none") and network_id == CALIBRATED_NETWORK,
                         watch=watch, act=act)
    hours = shown.pop("expected_unsafe_hours") or {
        "mean": round(res.expected_unsafe_hours, 2), "p10": round(res.unsafe_hours_p10, 2), "p90": round(res.unsafe_hours_p90, 2)}
    return {
        "date": date, "network": network_id, "rule": r.id, "fix": fix or "none", **shown,
        "t": labels, "thresholds": {"watch": watch, "act": act}, "expected_unsafe_hours": hours,
        "peak_voltage_v": {k: round(v, 1) for k, v in res.peak_voltage_v.items()},
        "window_risk": {WINDOW_KEYS[k]: round(v, 3) for k, v in res.window_risk.items()},
        "shares": {SHARE_KEYS[k]: round(v, 3) for k, v in res.shares.items()},
        "n_scenarios": res.n_scenarios, "provenance": provenance(date),
        "calibration": {**cal, "applied": shown["series"] == "calibrated"},
    }


CALIBRATED_NETWORK = "benchmark_250"


def shown_series(cal: dict, raw: list[float], dark: list[float], times: list[str], *, applies: bool,
                 watch: float = 0.20, act: float = 0.50) -> dict:
    """The chance series users see and everything derived from it (DECISIONS.md, F2).

    Calibrated when the held-out check passed (`cal["reliable"]`) and the request is where the map was fitted
    (`applies`), raw otherwise. Level, first watch and first act use the shown series. The no-solar series is scaled
    step by step by calibrated / raw, so the grid and solar parts of each bar keep their shares; a step with raw 0 has
    no solar part. Calibrated expected hours are the sum of the shown chances; their P10 to P90 range is None, because
    the scenario spread describes the raw draws. Raw series return expected hours None (the engine's values stand)."""
    calibrated = bool(cal.get("reliable")) and applies
    p = [round(float(x), 3) for x in (cal["calibrated"] if calibrated else raw)]
    if calibrated:
        p_dark = [round(c if r <= 0 else c * min(d, r) / r, 3) for c, r, d in zip(p, raw, dark)]
        hours = {"mean": round(sum(p) * 0.25, 2), "p10": None, "p90": None}
    else:
        p_dark, hours = list(dark), None
    first = lambda th: next((times[i] for i, x in enumerate(p) if x >= th), None)  # noqa: E731
    level = "act" if first(act) else "watch" if first(watch) else "ok"
    return {"series": "calibrated" if calibrated else "raw", "p_unsafe": p, "p_unsafe_without_solar": p_dark,
            "level": level, "first_watch": first(watch), "first_act": first(act), "expected_unsafe_hours": hours}


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
            "scenarios": list(scn.labels), "provenance": provenance(date)}


# ---- /simulate -------------------------------------------------------------------------------------------------

def simulate_payload(date: str, network_id: str, rule_id: str, fix: str = "none", *, n: int = N_SCENARIOS) -> dict:
    """The design-case day (P90 sun) without and with one fix, step by step."""
    net, r = network(network_id), rule(rule_id)
    design = _design(robust_set(scenarios(date, net, n)))
    solver = DaySolver(net, asymmetric=True)
    runs = {"before": solver.solve(design), "after": solver.solve(design, _controls(fix))}
    out = {"date": date, "network": network_id, "rule": r.id, "fix": fix, "t": _labels(design.t),
           "limits_v": {"min": r.vmin_v, "max": r.vmax_v}, "provenance": provenance(date)}
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
    return {"date": date, "network": network_id, "adoption": adoption, **out, "provenance": provenance(date)}


def connection_payload(date: str, network_id: str, rule_id: str, node: int, kw: float, count: int,
                       phase: str | None, adoption: float = DEFAULT_ADOPTION) -> dict:
    from engine.headroom import check_connection
    net, design = planning_street(date, network_id, adoption)
    try:
        out = check_connection(net, design, rule(rule_id), node=node, kw=kw, count=count,
                               phase=None if phase is None else PHASE.index(phase))
    except ValueError as exc:
        raise ApiError(422, str(exc), details={"valid_nodes": [int(n) for n in net.lv_nodes]}) from exc
    return {"date": date, "network": network_id, "adoption": adoption, **out, "provenance": provenance(date)}


def hosting_payload(date: str, network_id: str, rule_id: str, draws: int = 30) -> dict:
    """P10/P50/P90 hosting capacity on the design-case day, without a fix and with standard Volt/VAR."""
    from engine.hosting import hosting_capacity
    net = network(network_id)
    design = _design(robust_set(scenarios(date, net)))
    r = rule(rule_id)
    return {"date": date, "network": network_id, "rule": r.id,
            "without_fix": hosting_capacity(net, design, r, draws=draws),
            "with_volt_var": hosting_capacity(net, design, r, draws=draws, controls=Controls(volt_var=_VV)),
            "provenance": provenance(date)}


# ---- planning extras (/meter-sites, /rx-map, /transformers) -----------------------------------------------------

METER_SITES_SHOWN = 10
HEADROOM_SEARCH_KW = 60.0                  # engine.headroom.headroom's max_kw default


def meter_sites_payload(date: str, network_id: str, rule_id: str, adoption: float = DEFAULT_ADOPTION) -> dict:
    """E4: where one smart meter reveals the most (voltage rise per kW at the peak step x homes downstream)."""
    from engine.planning_extra import PROBE_KW, rank_meter_sites
    net, design = planning_street(date, network_id, adoption)
    rows = rank_meter_sites(net, design)
    return {"date": date, "network": network_id, "rule": rule(rule_id).id, "adoption": adoption,
            "sites": rows[:METER_SITES_SHOWN], "n_candidates": len(rows), "probe_kw": PROBE_KW, "provenance": provenance(date)}


def rx_map_payload(date: str, network_id: str, rule_id: str, adoption: float = DEFAULT_ADOPTION) -> dict:
    """E6: peak voltage with and without standard Volt/VAR as line resistance and reactance are scaled."""
    from engine.planning_extra import rx_map
    net, design = planning_street(date, network_id, adoption)
    r = rule(rule_id)
    return {"date": date, "network": network_id, "adoption": adoption, "vmax_v": r.vmax_v,
            **rx_map(net, design, r), "provenance": provenance(date)}


def transformers_payload(date: str, rule_id: str, adoption: float = DEFAULT_ADOPTION) -> dict:
    """P7.7: the street archetypes as a demo portfolio, ordered by the share of their safe room already used.

    Connected kW is the solar each street has at `adoption`. Whether a transformer is metered is not known for the
    archetypes, so all are treated as unmetered; a utility's own list sets it (docs/ONBOARDING.md)."""
    from engine.planning_extra import rank_transformers
    portfolio = []
    for archetype_id in ARCHETYPES:
        net, design = planning_street(date, archetype_id, adoption)
        portfolio.append({"id": archetype_id, "network": net, "scenarios": design,
                          "connected_kw": round(float(net.house_kwp.sum()), 1), "metered": False})
    rows = rank_transformers(portfolio, rule(rule_id))
    for row in rows:
        row["label"] = ARCHETYPES[row["id"]].label
        row["at_search_limit"] = row["headroom_kw"] >= HEADROOM_SEARCH_KW     # the bisection stops at this size
    return {"date": date, "rule": rule(rule_id).id, "adoption": adoption, "transformers": rows,
            "search_limit_kw": HEADROOM_SEARCH_KW,
            "metering": "unknown for the archetypes: all treated as unmetered", "provenance": provenance(date)}


# ---- /street: the street as a picture, quarter hour by quarter hour ---------------------------------------------

def _candidate(fix: str, net, scn, r):
    """The fix as a tournament candidate: a simple setting directly, anything else from the catalogue."""
    from engine.fixes.base import Candidate
    from engine.fixes.catalog import build as build_catalog
    if fix in SIMPLE_FIXES:
        return Candidate(fix, fix, "simple", net, controls=SIMPLE_FIXES[fix])
    for c in build_catalog(net, scn, r):
        if c.id == fix:
            return c
    raise ApiError(404, f"unknown fix {fix!r}", details={"simple": sorted(SIMPLE_FIXES)})


def _street_run(candidate, design, r) -> dict:
    from engine.street import home_net_kw, line_ends, line_flows
    res = _solve(candidate, design, r)
    v = evaluate(res, r)
    net = candidate.network
    flows = line_flows(net, home_net_kw(net, design, candidate.controls))
    lv = list(net.lv_nodes)
    home_v = res.u_pu[0][:, [lv.index(int(n)) for n in net.house_node], net.house_phase] * NOMINAL_V   # (T, H)
    return {
        "home_v": np.round(home_v, 1).tolist(),
        "home_phase": [PHASE[p] for p in net.house_phase],
        "line_ends": line_ends(net),                      # [parent, child] per line of this run's own network
        "line_phase_kw": np.round(flows["phase_kw"].transpose(1, 0, 2), 1).tolist(),     # (T, L, 3)
        "line_neutral_a": np.round(flows["neutral_a"].T, 1).tolist(),                     # (T, L)
        "line_loading_pct": np.round(res.line_loading_pct[0], 1).tolist(),
        "trafo_kw": [round(float(x), 1) for x in res.trafo_p_kw[0]],
        "trafo_loading_pct": [round(float(x), 1) for x in res.trafo_loading_pct[0]],
        "solar_kw": [round(float(x), 1) for x in res.pv_kw[0]],
        "neutral_a": [round(float(x), 1) for x in res.neutral_a[0]],
        "unsafe": [bool(x) for x in v.unsafe[0]],
        "summary": summarise(res, v),
    }


def street_payload(date: str, network_id: str, rule_id: str, fix: str = "none", *, n: int = N_SCENARIOS) -> dict:
    """The design day (highest-sun case of tomorrow's scenarios) on a schematic of the street, without and with a fix."""
    from engine.street import layout
    from engine.fixes.base import Candidate
    net, r = network(network_id), rule(rule_id)
    scn = robust_set(scenarios(date, net, n))
    design = _design(scn)
    base = Candidate("none", "none", "none", net)
    out = {"date": date, "network": network_id, "rule": r.id, "fix": fix, "t": _labels(design.t),
           "limits_v": {"min": r.vmin_v, "max": r.vmax_v}, "layout": layout(net),
           "homes": [{"node": int(nd), "kwp": round(float(k), 2)} for nd, k in zip(net.house_node, net.house_kwp)],
           "trafo_kva": round(net.trafo.sn_va / 1000, 1), "before": _street_run(base, design, r),
           "flow_method": "estimated from each home's net power (demand minus delivered solar); losses ignored",
           "provenance": provenance(date)}
    if fix != "none":
        c = _candidate(fix, net, scn, r)
        out["fix_label"] = c.label
        out["after"] = _street_run(c, design, r)
    return out
