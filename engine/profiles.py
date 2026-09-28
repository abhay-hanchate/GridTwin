"""Turn raw CEEW meter readings and Open-Meteo weather into 15-minute profiles.

All timestamps are naive local time (IST), 15-minute resolution.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from engine import config

CEEW_COLUMNS = ["ts", "kwh", "v", "a", "hz", "meter"]


def read_ceew(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=[0])
    df.columns = CEEW_COLUMNS
    lo, hi = config.VALID_VOLTAGE_RANGE_V
    valid = df["v"].between(lo, hi)
    # A zero or impossible voltage means the meter was off (outage), not zero demand.
    df.loc[~valid, ["kwh", "v"]] = np.nan
    return df[["ts", "kwh", "v", "meter"]]


def load_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """Household demand in kW, one column per meter (3-minute kWh x 20 = kW)."""
    kw = df.assign(kw=df["kwh"] * 20).pivot_table(index="ts", columns="meter", values="kw")
    kw = kw.resample("15min").mean()
    return kw.ffill(limit=4).astype("float32")


def voltage_profile(df: pd.DataFrame) -> pd.Series:
    """Median customer voltage across meters, in per unit of 230 V."""
    v = df.dropna(subset=["v"]).set_index("ts")["v"].resample("15min").median()
    return (v / config.NOMINAL_VOLTAGE_V).rename("upstream_vm_pu").astype("float32")


def voltage_stats(df: pd.DataFrame) -> dict:
    v = df["v"].dropna()
    nominal = config.NOMINAL_VOLTAGE_V
    return {
        "meters": int(df["meter"].nunique()),
        "readings": int(len(v)),
        "median_v": round(float(v.median()), 1),
        "share_above_6pct": round(float((v > nominal * 1.06).mean()), 4),
        "share_above_10pct": round(float((v > nominal * 1.10).mean()), 4),
        "share_below_10pct": round(float((v < nominal * 0.90).mean()), 4),
    }


def read_weather(path: Path) -> pd.DataFrame:
    hourly = json.loads(path.read_text())["hourly"]
    w = pd.DataFrame(hourly)
    w["time"] = pd.to_datetime(w["time"])
    return w.set_index("time")


def pv_from_weather(w: pd.DataFrame) -> pd.Series:
    """Solar output in kW per installed kW (PVWatts model), 15-minute, from hourly weather.

    Open-Meteo radiation is the mean of the preceding hour, so the sun position is
    evaluated at the middle of that hour.
    """
    mid = (w.index - pd.Timedelta(minutes=30)).tz_localize(config.TIMEZONE)
    site = pvlib.location.Location(config.LATITUDE, config.LONGITUDE, config.TIMEZONE, config.ALTITUDE_M)
    sun = site.get_solarposition(mid)
    poa = pvlib.irradiance.get_total_irradiance(
        config.PV_TILT_DEG, config.PV_AZIMUTH_DEG,
        sun["apparent_zenith"].values, sun["azimuth"].values,
        w["direct_normal_irradiance"].values, w["shortwave_radiation"].values, w["diffuse_radiation"].values,
    )
    params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["close_mount_glass_glass"]
    t_cell = pvlib.temperature.sapm_cell(
        poa["poa_global"], w["temperature_2m"].values, w["wind_speed_10m"].values / 3.6, **params
    )
    dc = pvlib.pvsystem.pvwatts_dc(poa["poa_global"], t_cell, 1.0, config.PV_GAMMA_PDC)
    ac = np.clip(np.nan_to_num(dc) * (1 - config.PV_SYSTEM_LOSSES), 0, 1)
    hourly = pd.Series(ac, index=w.index, name="pv_kw_per_kwp")
    return hourly.resample("15min").interpolate("time").clip(lower=0).astype("float32")
