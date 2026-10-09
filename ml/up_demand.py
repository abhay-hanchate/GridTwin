"""Uttar Pradesh state demand: the live signal behind the day-ahead demand and voltage forecasts.

Live: the UP load dispatch centre (UPSLDC) publishes the state's demand every 3 minutes for yesterday and today.
History: daily UP energy met from Grid-India reports, 2013 to April 2024 (Zenodo record 14983362, CC BY 4.0).

The forecasts use a scale-free anchor, `up_ratio`: yesterday's UP energy against the week before it, so a scale
difference between the two sources cancels out.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from engine import config

LOAD_GRAPH_URL = "https://www.upsldc.org/assets/dataset/scada-load-graph.json"
HISTORY_PATH = config.RAW_DIR / "zenodo_state_demand" / "corrected_daily_energy_met_MU.csv"
HISTORY_URL = "https://zenodo.org/api/records/14983362/files/corrected_daily_energy_met_MU.csv/content"
LIVE_PATH = config.ROOT / "data" / "live" / "up_demand.parquet"
POINTS_PER_DAY = 480                 # one reading every 3 minutes
COMPLETE_SHARE = 0.95                # a day counts once 95% of its readings exist
WINDOW_DAYS = 7
MIN_WINDOW_DAYS = 5                  # a missed recording day or a gap in the history does not blank the anchor


def fetch_load_graph(timeout: int = 60) -> dict:
    r = requests.get(LOAD_GRAPH_URL, timeout=timeout, headers={"User-Agent": "GridTwin research (daily fetch)"})
    r.raise_for_status()
    return r.json()


def parse_load_graph(payload: dict) -> pd.Series:
    """3-minute UP demand in MW with naive IST timestamps, for every date in the payload."""
    rows = [(pd.Timestamp(f"{day} {p['date']}"), float(p["demand"]))
            for day, points in payload["dataset"].items() for p in points if p.get("demand") is not None]
    s = pd.Series(dict(rows), name="demand_mw", dtype=float).sort_index()
    s.index.name = "ts"
    return s


def daily_energy(mw: pd.Series) -> pd.Series:
    """Energy per complete day in MU (million kWh): mean MW x 24 h / 1000."""
    days = mw.groupby(mw.index.normalize())
    complete = days.count() >= COMPLETE_SHARE * POINTS_PER_DAY
    return (days.mean()[complete] * 24 / 1000).rename("energy_mu")


def up_ratio(energy: pd.Series, min_days: int = MIN_WINDOW_DAYS) -> pd.Series:
    """For each target day d: E(d-1) / mean(E(d-8 .. d-2)); NaN without yesterday or with fewer than `min_days` of the
    seven days before. The index runs to one day after the last energy value, so tomorrow's ratio is known today."""
    e = energy.asfreq("D")
    e = e.reindex(pd.date_range(e.index[0], e.index[-1] + pd.Timedelta(days=1), freq="D"))
    week_before = e.shift(2).rolling(WINDOW_DAYS, min_periods=min_days).mean()
    return (e.shift(1) / week_before).rename("up_ratio")


def load_history(path: Path = HISTORY_PATH) -> pd.Series:
    """Daily UP energy met (MU); the source repeats some dates, which are averaged."""
    raw = pd.read_csv(path, parse_dates=["Date"])
    return raw.groupby("Date")["Uttar Pradesh"].mean().asfreq("D").rename("energy_mu")


def download_history(path: Path = HISTORY_PATH) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(HISTORY_URL, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def record(payload: dict, path: Path = LIVE_PATH) -> pd.Series:
    """Merge one fetch into the live record (later readings of the same minute win) and return the record."""
    new = parse_load_graph(payload)
    if path.exists():
        old = pd.read_parquet(path)["demand_mw"]
        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_frame().to_parquet(path)
    return new


def combined_energy(history: pd.Series, live: pd.Series) -> pd.Series:
    """One daily series: the live record where it exists, the Grid-India history elsewhere."""
    return live.combine_first(history).sort_index().rename("energy_mu")
