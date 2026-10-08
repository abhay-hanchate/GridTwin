"""A7: compute the yield factor of a measured plant against the modelled PV for the same site and period.

Usage:
  python -m scripts.calibrate_pv --csv data/raw/plant.csv --timestamp-col ts --power-col kw --unit kW --kwp 72 \
      --weather data/raw/weather_plant.json --lat 12.97 --lon 77.59 --alt 900
Writes data/processed/pv_yield_factor.json. The weather file is an Open-Meteo archive download for the plant's own
coordinates (same variables as config.WEATHER_VARS).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import config, profiles
from ml.pv_calibration import read_plant_csv, yield_factor


def calibrate(csv: Path, timestamp_col: str, power_col: str, unit: str, kwp: float, weather: Path, site: config.Site) -> dict:
    measured = read_plant_csv(csv, timestamp_col, power_col, unit=unit)
    modelled = profiles.pv_hourly(profiles.read_weather(weather), site)
    return yield_factor(measured, kwp, modelled)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--timestamp-col", required=True)
    ap.add_argument("--power-col", required=True)
    ap.add_argument("--unit", choices=("kW", "W"), default="kW")
    ap.add_argument("--kwp", type=float, required=True)
    ap.add_argument("--weather", type=Path, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--alt", type=float, default=0.0)
    ap.add_argument("--out", type=Path, default=config.PROCESSED_DIR / "pv_yield_factor.json")
    a = ap.parse_args()
    result = calibrate(a.csv, a.timestamp_col, a.power_col, a.unit, a.kwp, a.weather, config.Site(a.lat, a.lon, a.alt))
    a.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
