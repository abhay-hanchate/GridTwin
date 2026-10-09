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


def read_ceew_raw(path: Path) -> pd.DataFrame:
    """All readings exactly as recorded (the six files share one column order)."""
    df = pd.read_csv(path, parse_dates=[0])
    df.columns = CEEW_COLUMNS
    return df[["ts", "kwh", "v", "meter"]]


def clean_ceew(df: pd.DataFrame) -> pd.DataFrame:
    """A zero or impossible voltage means the meter was off (outage) or surged, not zero demand."""
    lo, hi = config.VALID_VOLTAGE_RANGE_V
    df = df.copy()
    df.loc[~df["v"].between(lo, hi), ["kwh", "v"]] = np.nan
    return df


def read_ceew(path: Path) -> pd.DataFrame:
    return clean_ceew(read_ceew_raw(path))


def quality_report(raw: pd.DataFrame) -> dict:
    """Outage, surge and coverage statistics before any cleaning."""
    lo, hi = config.VALID_VOLTAGE_RANGE_V
    v = raw["v"]
    flags = pd.DataFrame({"meter": raw["meter"], "outage": v < lo, "surge": v > hi, "valid": v.between(lo, hi)})
    per_meter = flags.groupby("meter")[["outage", "surge", "valid"]].mean().round(4)
    return {
        "readings": int(len(raw)),
        "meters": int(raw["meter"].nunique()),
        "first": raw["ts"].min().strftime("%Y-%m-%d %H:%M"),
        "last": raw["ts"].max().strftime("%Y-%m-%d %H:%M"),
        "outage_share": round(float((v < lo).mean()), 4),
        "surge_share": round(float((v > hi).mean()), 4),
        "max_voltage_v": round(float(v.max()), 1),
        "per_meter": per_meter.to_dict(orient="index"),
    }


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


def _location(site: config.Site | None) -> pvlib.location.Location:
    site = site or config.SITES["mathura"]
    return pvlib.location.Location(site.latitude, site.longitude, config.TIMEZONE, site.altitude_m)


def pv_from_weather(w: pd.DataFrame, site: config.Site | None = None) -> pd.Series:
    """Solar output in kW per installed kW, 15-minute, from hourly weather."""
    return pv_hourly(w, site).resample("15min").interpolate("time").clip(lower=0).astype("float32")


def pv_hourly(w: pd.DataFrame, site: config.Site | None = None) -> pd.Series:
    """Solar output in kW per installed kW (PVWatts model), hourly.

    Open-Meteo radiation is the mean of the preceding hour, so the sun position is
    evaluated at the middle of that hour.
    """
    mid = (w.index - pd.Timedelta(minutes=30)).tz_localize(config.TIMEZONE)
    sun = _location(site).get_solarposition(mid)
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
    return pd.Series(ac, index=w.index, name="pv_kw_per_kwp")


def clearsky_ghi(index: pd.DatetimeIndex, site: config.Site | None = None) -> pd.Series:
    """Clear-sky global horizontal irradiance (Ineichen) at mid-hour, W/m2."""
    mid = (index - pd.Timedelta(minutes=30)).tz_localize(config.TIMEZONE)
    return pd.Series(_location(site).get_clearsky(mid)["ghi"].to_numpy(), index=index, name="clearsky_ghi")
