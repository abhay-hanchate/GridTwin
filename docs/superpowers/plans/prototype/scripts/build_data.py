"""Build the processed profiles from data/raw.

Usage:  python scripts/download_data.py && python scripts/build_data.py

Outputs
  data/processed/v2/*_<district>.parquet|json   one set per district, every meter kept
  data/processed/*.parquet                      the Round 1 (legacy) Mathura files, rebuilt unchanged
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import config, profiles  # noqa: E402


def build_district(frames: list[pd.DataFrame], weather: pd.DataFrame, site: config.Site, out: Path, district: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.concat(frames)
    report = profiles.quality_report(raw)
    ceew = profiles.clean_ceew(raw)

    loads = profiles.load_profiles(ceew)
    loads.to_parquet(out / f"load_kw_{district}.parquet")
    profiles.voltage_profile(ceew).to_frame().to_parquet(out / f"upstream_vm_pu_{district}.parquet")
    weather.to_parquet(out / f"weather_hourly_{district}.parquet")
    profiles.pv_from_weather(weather, site).to_frame().to_parquet(out / f"pv_kw_per_kwp_{district}.parquet")

    coverage = loads.notna().groupby(loads.index.year).mean().T                  # meters x years
    report["coverage_by_year"] = coverage.round(3).rename(columns=str).to_dict(orient="index")
    report["voltage_by_year"] = {str(y): profiles.voltage_stats(g) for y, g in ceew.groupby(ceew["ts"].dt.year)}
    (out / f"quality_{district}.json").write_text(json.dumps(report, indent=2))
    return report


def build_legacy(raw_by_key: dict, out: Path) -> None:
    """Round 1 files: Mathura 2019 and 2021, meters kept by their 2019 coverage."""
    keys = [("mathura", 2019), ("mathura", 2021)]
    if not all(k in raw_by_key for k in keys):
        print("legacy files skipped (Mathura 2019 and 2021 not both downloaded)")
        return
    ceew = profiles.clean_ceew(pd.concat([raw_by_key[k] for k in keys]))
    loads = profiles.load_profiles(ceew)
    coverage = loads.loc[:"2019-12-31"].notna().mean()
    keep = coverage[coverage >= config.MIN_METER_COVERAGE].index
    loads[keep].to_parquet(out / "load_kw.parquet")
    print(f"legacy load_kw: {len(keep)} of {len(coverage)} meters kept, {len(loads)} steps")
    profiles.voltage_profile(ceew).to_frame().to_parquet(out / "upstream_vm_pu.parquet")
    stats = profiles.voltage_stats(ceew[ceew.ts < "2020-01-01"])
    (out / "voltage_stats.json").write_text(json.dumps(stats, indent=2))
    weather = profiles.read_weather(config.RAW_DIR / "weather_mathura.json")
    weather.to_parquet(out / "weather_hourly.parquet")
    profiles.pv_from_weather(weather).to_frame().to_parquet(out / "pv_kw_per_kwp.parquet")


def main() -> None:
    out = config.PROCESSED_DIR
    out.mkdir(parents=True, exist_ok=True)
    raw_by_key = {}
    for f in config.CEEW_FILES:
        path = config.RAW_DIR / f.filename
        if path.exists():
            raw_by_key[(f.district, f.year)] = profiles.read_ceew_raw(path)
        else:
            print(f"skip {f.filename} (run scripts/download_data.py)")
    for district in config.DISTRICTS:
        frames = [df for (d, _), df in raw_by_key.items() if d == district]
        if not frames:
            continue
        weather = profiles.read_weather(config.RAW_DIR / f"weather_{district}.json")
        rep = build_district(frames, weather, config.SITES[district], out / "v2", district)
        print(district, {k: rep[k] for k in ("meters", "readings", "outage_share", "surge_share", "max_voltage_v")})
    build_legacy(raw_by_key, out)


if __name__ == "__main__":
    main()
