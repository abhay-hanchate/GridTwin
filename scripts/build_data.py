"""Build the processed profiles in data/processed from data/raw.

Usage:  python scripts/download_data.py && python scripts/build_data.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import config, profiles  # noqa: E402


def main() -> None:
    out = config.PROCESSED_DIR
    out.mkdir(parents=True, exist_ok=True)

    ceew = pd.concat([profiles.read_ceew(config.RAW_DIR / name) for name in config.CEEW_FILES])

    loads = profiles.load_profiles(ceew)
    coverage = loads.loc[:"2019-12-31"].notna().mean()
    keep = coverage[coverage >= config.MIN_METER_COVERAGE].index
    loads[keep].to_parquet(out / "load_kw.parquet")
    print(f"load_kw: {len(keep)} of {len(coverage)} meters kept, {len(loads)} steps")

    profiles.voltage_profile(ceew).to_frame().to_parquet(out / "upstream_vm_pu.parquet")

    stats = profiles.voltage_stats(ceew[ceew.ts < "2020-01-01"])
    (out / "voltage_stats.json").write_text(json.dumps(stats, indent=2))
    print("voltage stats (2019):", stats)

    weather = profiles.read_weather(config.RAW_DIR / "weather_mathura.json")
    weather.to_parquet(out / "weather_hourly.parquet")
    pv = profiles.pv_from_weather(weather)
    pv.to_frame().to_parquet(out / "pv_kw_per_kwp.parquet")
    daily = pv.resample("D").sum() / 4
    print(f"pv: mean {daily.mean():.2f} kWh/kWp/day, peak {pv.max():.3f} kW/kWp")


if __name__ == "__main__":
    main()
