"""Download the raw datasets into data/raw (never committed).

Usage:  python scripts/download_data.py
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import config  # noqa: E402


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip  {dest.name} (already present)")
        return
    print(f"fetch {dest.name} ...", flush=True)
    part = dest.with_name(dest.name + ".part")     # an interrupted fetch never looks like a finished file
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    part.replace(dest)
    print(f"done  {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")


LEGACY_NAMES = {("mathura", 2019): "mathura2019.csv", ("mathura", 2021): "mathura2021.csv"}


def weather_url(base: str, start: str, end: str, site: config.Site = config.SITES["mathura"]) -> str:
    return (
        f"{base}?latitude={site.latitude}&longitude={site.longitude}"
        f"&start_date={start}&end_date={end}"
        f"&hourly={','.join(config.WEATHER_VARS)}&timezone={config.TIMEZONE}"
    )


ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"


def main() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for f in config.CEEW_FILES:
        legacy = config.RAW_DIR / LEGACY_NAMES.get((f.district, f.year), "")
        target = config.RAW_DIR / f.filename
        if legacy.is_file() and not target.exists():
            legacy.rename(target)                      # Round 1 file names are migrated, not downloaded again
        download(f.url, target)
    for district, site in config.SITES.items():
        download(weather_url(ARCHIVE, config.WEATHER_START, config.WEATHER_END, site),
                 config.RAW_DIR / f"weather_{district}.json")
    # ML training data for Mathura: genuine day-ahead forecasts (issued the day before) and ERA5 reanalysis.
    day_ahead_vars = ",".join(f"{v}_previous_day1" for v in config.WEATHER_VARS)
    download(weather_url(PREVIOUS_RUNS, "2024-01-01", "2025-12-31").replace(
        f"hourly={','.join(config.WEATHER_VARS)}", f"hourly={day_ahead_vars}"),
        config.RAW_DIR / "dayahead_mathura_2024_2025.json")
    download(weather_url(ARCHIVE, "2024-01-01", "2025-12-31") + "&models=era5",
             config.RAW_DIR / "era5_mathura_2024_2025.json")


if __name__ == "__main__":
    main()
