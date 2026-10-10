"""Evening run: precompute what the dashboard serves, and log tomorrow's live solar forecast for the drift monitor.

Usage:  python -m scripts.nightly [--networks benchmark_250] [--rules pm10 up_2005] [--force] [--no-live]

Writes data/results/v2/<cache key>.json for /risk and /fixes on three demo dates (sunny, mixed, cloudy, picked from
the solar v2 2025 forecast); on the sunny one also the planning routes (/headroom, /hosting, /meter-sites, /rx-map)
for every street archetype and /transformers for the portfolio; and data/results/v2/index.json. These files are what
GRIDTWIN_OFFLINE=1 serves. One data/results/planning_<archetype>.json per archetype summarises headroom and hosting
capacity under each rule.
Then fetches tomorrow's multi-model solar forecast and records it with scripts.monitor.log_forecast; a network
failure there is reported and does not fail the run.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.cache import load_or_compute
from backend.v2 import compute
from backend.v2.jobs import cache_key
from backend.v2.settings import Settings
from engine.archetypes import ARCHETYPES

SUNNY = "2025-05-15"          # the documented demo day (the Round 1 early-warning date)


def demo_dates(forecast: pd.DataFrame) -> dict[str, str]:
    """Sunny is fixed; cloudy is the monsoon day with the least forecast solar; mixed is closest to the year's median."""
    daily = forecast["p50"].resample("D").sum()
    daily = daily[daily > 0]
    monsoon = daily[daily.index.month.isin([6, 7, 8, 9])]
    cloudy = monsoon.idxmin() if len(monsoon) else daily.idxmin()
    mixed = (daily - daily.median()).abs().idxmin()
    return {"sunny": SUNNY, "mixed": mixed.strftime("%Y-%m-%d"), "cloudy": cloudy.strftime("%Y-%m-%d")}


def precompute(settings: Settings, networks: list[str], rules: list[str], force: bool = False,
               planning_networks: list[str] | None = None, live: bool = False) -> list[dict]:
    """`live` adds the real tomorrow (live weather forecast) to the archive days, so the dashboard opens instantly."""
    from backend.v2.live_inputs import is_live, today_ist
    out_dir = settings.results_dir / "v2"
    planning_networks = list(ARCHETYPES) if planning_networks is None else planning_networks
    dates = demo_dates(compute._solar_table())
    if live:
        dates = {"tomorrow": (today_ist() + timedelta(days=1)).isoformat(), **dates}
    entries = []
    jobs = [("risk", lambda d, n, r: compute.risk_payload(d, n, r, "none"), {"fix": "none"}),
            ("fixes", lambda d, n, r: compute.fixes_payload(d, n, r), {})]
    adoption = {"adoption": compute.DEFAULT_ADOPTION}
    planning = [("headroom", lambda d, n, r: compute.headroom_payload(d, n, r, compute.DEFAULT_ADOPTION), adoption),
                ("hosting", lambda d, n, r: compute.hosting_payload(d, n, r), {}),
                ("meter-sites", lambda d, n, r: compute.meter_sites_payload(d, n, r, compute.DEFAULT_ADOPTION), adoption),
                ("rx-map", lambda d, n, r: compute.rx_map_payload(d, n, r, compute.DEFAULT_ADOPTION), adoption)]

    def run(route, fn, kind, day, rule_id, network=None, **extra):
        params = {"date": day, **({"network": network} if network else {}), "rule": rule_id, **extra}
        if is_live(day):
            params["issued"] = today_ist().isoformat()         # the key the API uses for a live day
        key = cache_key(route, settings.code_version, **params)
        path = out_dir / f"{key}.json"
        if force and path.exists():
            path.unlink()
        started = time.perf_counter()
        result = load_or_compute(out_dir, key, fn)
        seconds = round(time.perf_counter() - started, 1)
        summary = (result.get("level") or result.get("verdict", {}).get("message")
                   or result.get("without_fix", {}).get("adoption_share") or "")
        print(f"{route:12s} {kind:6s} {day} {network or 'portfolio'} {rule_id:8s} {seconds:6.1f}s  {summary}", flush=True)
        entries.append({"route": route, "date": day, "day_type": kind, "key": key, **params})
        return result

    for kind, day in dates.items():
        for network in networks:
            for rule in rules:
                rule_id = compute.rule(rule).id
                out = {route: run(route, lambda fn=fn: fn(day, network, rule_id), kind, day, rule_id, network, **extra)
                       for route, fn, extra in jobs}
                # the street animation: the day as it is, and with the fix the Fixes page opens first
                verdict = out["fixes"].get("verdict", {})
                for fix in dict.fromkeys(["none", verdict.get("recommended") or verdict.get("closest") or "none"]):
                    run("street", lambda fix=fix: compute.street_payload(day, network, rule_id, fix), kind, day, rule_id, network, fix=fix)
    for network in networks if "tomorrow" in dates else []:
        for rule in rules:
            rule_id = compute.rule(rule).id
            for route, fn, extra in planning:
                run(route, lambda fn=fn: fn(dates["tomorrow"], network, rule_id), "tomorrow", dates["tomorrow"], rule_id, network, **extra)
            run("transformers", lambda: compute.transformers_payload(dates["tomorrow"], rule_id, compute.DEFAULT_ADOPTION), "tomorrow",
                dates["tomorrow"], rule_id, adoption=compute.DEFAULT_ADOPTION)
    day = dates["sunny"]
    for network in planning_networks:
        summary = {"network": network, "label": ARCHETYPES[network].label, "date": day, "rules": {}}
        for rule in rules:
            rule_id = compute.rule(rule).id
            out = {route: run(route, lambda fn=fn: fn(day, network, rule_id), "sunny", day, rule_id, network, **extra)
                   for route, fn, extra in planning}
            summary["rules"][rule_id] = planning_summary(out["headroom"], out["hosting"])
        (settings.results_dir / f"planning_{network}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for rule in rules:
        rule_id = compute.rule(rule).id
        run("transformers", lambda: compute.transformers_payload(day, rule_id, compute.DEFAULT_ADOPTION), "sunny", day,
            rule_id, **adoption)
    entries += precompute_whatif(settings, dates["sunny"], networks[0], force)
    index = {"generated_at": datetime.now(timezone.utc).isoformat(), "code_version": settings.code_version,
             "demo_dates": dates, "entries": entries}
    (out_dir / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return entries


def prune(out_dir: Path, entries: list[dict]) -> list[str]:
    """Delete cached results the index does not name (older code versions nothing can reach) and return their names.

    A file of the current code version that is not indexed (a result computed on demand) is deleted too, so this only
    runs on request (--prune), after a full precompute."""
    keep = {f"{e['key']}.json" for e in entries} | {"index.json"}
    removed = sorted(f.name for f in out_dir.glob("*.json") if f.name not in keep)
    for name in removed:
        (out_dir / name).unlink()
    return removed


def planning_summary(headroom: dict, hosting: dict) -> dict:
    """Headline planning numbers of one archetype and rule: headroom per location and phase, hosting P10/P50/P90."""
    return {"baseline_unsafe_steps": headroom.get("baseline_unsafe_steps"),
            "headroom_kw": {where: {ph: v["no_worse_kw"] for ph, v in loc["phases"].items()}
                            for where, loc in headroom.get("locations", {}).items()},
            "hosting_share": {case: hosting.get(case, {}).get("adoption_share") for case in ("without_fix", "with_volt_var")}}


# Two example changes for the "Try a change" page, so it can show something with GRIDTWIN_OFFLINE=1.
WHATIF_EXAMPLES = [
    {"label": "Standard smart inverters (IEEE 1547 Volt/VAR)", "changes": [], "fixes": [{"id": "fix.volt_var"}]},
    {"label": "Evening EV charging at 20% of homes, with transformer tap +1",
     "changes": [{"id": "change.ev_charging", "params": {"share_of_homes": 0.2}}], "fixes": [{"id": "fix.tap"}]},
]


def precompute_whatif(settings: Settings, day: str, network: str, force: bool = False) -> list[dict]:
    from backend.v2.jobs import JobStore
    from backend.v2.routes_whatif import WhatIf, normalise, whatif_payload
    store, out_dir, entries = JobStore(settings.results_dir), settings.results_dir / "v2", []
    for example in WHATIF_EXAMPLES:
        spec = WhatIf(date=day, network=network, rule="pm10", changes=example["changes"], fixes=example["fixes"])
        norm, key = normalise(spec, settings, store)
        if force and (out_dir / f"{key}.json").exists():
            (out_dir / f"{key}.json").unlink()
        started = time.perf_counter()
        load_or_compute(out_dir, key, lambda norm=norm: whatif_payload(**norm))
        print(f"whatif {day} {example['label']}: {time.perf_counter() - started:.1f}s", flush=True)
        entries.append({"route": "whatif", "date": day, "day_type": "sunny", "key": key, "label": example["label"],
                        "network": norm["network"], "rule": norm["rule"],
                        "spec": {k: norm[k] for k in ("network", "rule", "adoption", "changes", "fixes")}})
    return entries


def log_live_forecast() -> str:
    """Fetch tomorrow's solar v2 forecast and record it for the drift monitor (P10.6)."""
    from ml import live_solar_v2 as live
    from scripts.monitor import log_forecast
    target = live.tomorrow_local()
    forecast, source = live.predict_live(live.frames_from_payload(live.fetch_payload(target), target), target)
    manifest = json.loads((live.MODEL_DIR / "solar_v2_manifest.json").read_text(encoding="utf-8"))
    import inspect
    # Solar v2 on v2/build widens per season and takes the target date; older versions take no date.
    takes_target = "target" in inspect.signature(live._conformal_q).parameters
    q_used, _ = live._conformal_q(manifest, live.STATE_PATH, target) if takes_target else         live._conformal_q(manifest, live.STATE_PATH)
    index = pd.date_range(pd.Timestamp(target), periods=len(forecast), freq="15min")
    log_forecast(forecast.set_axis(index), q_used)
    return f"logged {target} ({source})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--networks", nargs="+", default=["benchmark_250"])
    ap.add_argument("--planning-networks", nargs="+", default=None, help="default: every archetype")
    ap.add_argument("--rules", nargs="+", default=["pm10", "up_2005"])
    ap.add_argument("--force", action="store_true", help="recompute even when a cached result exists")
    ap.add_argument("--no-live", action="store_true", help="skip the live forecast (no network)")
    ap.add_argument("--prune", action="store_true", help="delete cached results the new index does not name")
    args = ap.parse_args()
    settings = Settings()
    entries = precompute(settings, args.networks, args.rules, args.force, args.planning_networks, live=not args.no_live)
    print(f"{len(entries)} results precomputed, code version {settings.code_version}")
    if args.prune:
        print(f"pruned {len(prune(settings.results_dir / 'v2', entries))} unindexed cached results")
    if not args.no_live:
        try:
            print(log_live_forecast())
        except Exception as exc:                 # the precomputed demo must not depend on the network
            print(f"live forecast not logged: {exc}")


if __name__ == "__main__":
    main()
