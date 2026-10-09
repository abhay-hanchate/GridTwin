"""Evening run: precompute what the dashboard serves, and log tomorrow's live solar forecast for the drift monitor.

Usage:  python -m scripts.nightly [--networks benchmark_250] [--rules pm10 up_2005] [--force] [--no-live]

Writes data/results/v2/<cache key>.json for /risk and /fixes on three demo dates (and /headroom and
/hosting on the sunny one) (sunny, mixed, cloudy, picked from
the solar v2 2025 forecast) and data/results/v2/index.json. These files are what GRIDTWIN_OFFLINE=1 serves.
Then fetches tomorrow's multi-model solar forecast and records it with scripts.monitor.log_forecast; a network
failure there is reported and does not fail the run.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import pandas as pd

from backend.cache import load_or_compute
from backend.v2 import compute
from backend.v2.jobs import cache_key
from backend.v2.settings import Settings

SUNNY = "2025-05-15"          # the documented demo day (the Round 1 early-warning date)


def demo_dates(forecast: pd.DataFrame) -> dict[str, str]:
    """Sunny is fixed; cloudy is the monsoon day with the least forecast solar; mixed is closest to the year's median."""
    daily = forecast["p50"].resample("D").sum()
    daily = daily[daily > 0]
    monsoon = daily[daily.index.month.isin([6, 7, 8, 9])]
    cloudy = monsoon.idxmin() if len(monsoon) else daily.idxmin()
    mixed = (daily - daily.median()).abs().idxmin()
    return {"sunny": SUNNY, "mixed": mixed.strftime("%Y-%m-%d"), "cloudy": cloudy.strftime("%Y-%m-%d")}


def precompute(settings: Settings, networks: list[str], rules: list[str], force: bool = False) -> list[dict]:
    out_dir = settings.results_dir / "v2"
    dates = demo_dates(compute._solar_table())
    entries = []
    jobs = [("risk", lambda d, n, r: compute.risk_payload(d, n, r, "none"), {"fix": "none"}),
            ("fixes", lambda d, n, r: compute.fixes_payload(d, n, r), {})]
    planning = [("headroom", lambda d, n, r: compute.headroom_payload(d, n, r, compute.DEFAULT_ADOPTION),
                 {"adoption": compute.DEFAULT_ADOPTION}),
                ("hosting", lambda d, n, r: compute.hosting_payload(d, n, r), {})]
    for kind, day in dates.items():
        for network in networks:
            for rule in rules:
                rule_id = compute.rule(rule).id
                for route, fn, extra in jobs + (planning if kind == "sunny" else []):
                    params = {"date": day, "network": network, "rule": rule_id, **extra}
                    key = cache_key(route, settings.code_version, **params)
                    path = out_dir / f"{key}.json"
                    if force and path.exists():
                        path.unlink()
                    started = time.perf_counter()
                    result = load_or_compute(out_dir, key, lambda: fn(day, network, rule_id))
                    seconds = round(time.perf_counter() - started, 1)
                    summary = (result.get("level") or result.get("verdict", {}).get("message")
                               or result.get("without_fix", {}).get("adoption_share") or "")
                    print(f"{route:5s} {kind:6s} {day} {network} {rule_id:8s} {seconds:6.1f}s  {summary}", flush=True)
                    entries.append({"route": route, "date": day, "day_type": kind, "key": key, **params})
    index = {"generated_at": datetime.now(timezone.utc).isoformat(), "code_version": settings.code_version,
             "demo_dates": dates, "entries": entries}
    (out_dir / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return entries


def log_live_forecast() -> str:
    """Fetch tomorrow's solar v2 forecast and record it for the drift monitor (P10.6)."""
    from ml import live_solar_v2 as live
    from scripts.monitor import log_forecast
    target = live.tomorrow_local()
    forecast, source = live.predict_live(live.frames_from_payload(live.fetch_payload(target), target), target)
    manifest = json.loads((live.MODEL_DIR / "solar_v2_manifest.json").read_text(encoding="utf-8"))
    q_used, _ = live._conformal_q(manifest, live.STATE_PATH)
    index = pd.date_range(pd.Timestamp(target), periods=len(forecast), freq="15min")
    log_forecast(forecast.set_axis(index), q_used)
    return f"logged {target} ({source})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--networks", nargs="+", default=["benchmark_250"])
    ap.add_argument("--rules", nargs="+", default=["pm10", "up_2005"])
    ap.add_argument("--force", action="store_true", help="recompute even when a cached result exists")
    ap.add_argument("--no-live", action="store_true", help="skip the live forecast (no network)")
    args = ap.parse_args()
    settings = Settings()
    entries = precompute(settings, args.networks, args.rules, args.force)
    print(f"{len(entries)} results precomputed, code version {settings.code_version}")
    if not args.no_live:
        try:
            print(log_live_forecast())
        except Exception as exc:                 # the precomputed demo must not depend on the network
            print(f"live forecast not logged: {exc}")


if __name__ == "__main__":
    main()
