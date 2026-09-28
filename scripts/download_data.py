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


def weather_url() -> str:
    return (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
        f"&start_date={config.WEATHER_START}&end_date={config.WEATHER_END}"
        f"&hourly={','.join(config.WEATHER_VARS)}&timezone={config.TIMEZONE}"
    )


def main() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in config.CEEW_FILES.items():
        download(url, config.RAW_DIR / name)
    download(weather_url(), config.RAW_DIR / "weather_mathura.json")


if __name__ == "__main__":
    main()
