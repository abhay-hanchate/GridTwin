"""Download the multi-model day-ahead weather used by solar v2 into data/raw (never committed).

Usage:  python -m scripts.download_solar_v2 [--district mathura]

One file per NWP model (Open-Meteo previous-runs API, `previous_day1` = issued the day before). A model that the
API does not carry for the period comes back with empty values; `ml.solar_v2.availability` (gate G2) drops it.
Open-Meteo API terms are unchecked (gate G6): read them before any use beyond the competition build.
"""
from __future__ import annotations

import argparse
import time

import requests

from engine import config
from ml import solar_v2

PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
START, END = "2024-01-01", "2025-12-31"


def request_params(site: config.Site, model: str | None) -> dict:
    params = {"latitude": site.latitude, "longitude": site.longitude, "timezone": config.TIMEZONE,
              "start_date": START, "end_date": END,
              "hourly": ",".join(f"{v}_previous_day1" for v in config.WEATHER_VARS)}
    if model is not None:
        params["models"] = model
    return params


def fetch(site: config.Site, model: str | None, dest, attempts: int = 4) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"skip  {dest.name}")
        return True
    for attempt in range(attempts):
        r = requests.get(PREVIOUS_RUNS, params=request_params(site, model), timeout=180)
        if r.status_code == 200:
            dest.write_text(r.text)
            print(f"done  {dest.name} ({len(r.text) / 1e6:.1f} MB)")
            return True
        print(f"retry {dest.name}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(5 * (attempt + 1))
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", default="mathura", choices=config.DISTRICTS)
    args = ap.parse_args()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    site = config.SITES[args.district]
    failed = [m for m in (None, *solar_v2.CANDIDATE_MODELS)
              if not fetch(site, m, solar_v2.raw_path(m, args.district))]
    if failed:
        raise SystemExit(f"could not download: {failed}")


if __name__ == "__main__":
    main()
