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
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"done  {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")


def weather_url(base: str, start: str, end: str) -> str:
    return (
        f"{base}?latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
        f"&start_date={start}&end_date={end}"
        f"&hourly={','.join(config.WEATHER_VARS)}&timezone={config.TIMEZONE}"
    )


ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"


def main() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in config.CEEW_FILES.items():
        download(url, config.RAW_DIR / name)
    download(weather_url(ARCHIVE, config.WEATHER_START, config.WEATHER_END), config.RAW_DIR / "weather_mathura.json")
    # ML training data: genuine day-ahead forecasts (issued the day before) and ERA5 reanalysis.
    day_ahead_vars = ",".join(f"{v}_previous_day1" for v in config.WEATHER_VARS)
    download(weather_url(PREVIOUS_RUNS, "2024-01-01", "2025-12-31").replace(
        f"hourly={','.join(config.WEATHER_VARS)}", f"hourly={day_ahead_vars}"),
        config.RAW_DIR / "dayahead_mathura_2024_2025.json")
    download(weather_url(ARCHIVE, "2024-01-01", "2025-12-31") + "&models=era5",
             config.RAW_DIR / "era5_mathura_2024_2025.json")


if __name__ == "__main__":
    main()
