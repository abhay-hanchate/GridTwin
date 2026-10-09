"""Shared constants: location, data sources, file paths and grid limits."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CACHE_DIR = ROOT / "data" / "cache"

# Mathura, Uttar Pradesh: the CEEW smart meters and the weather come from the same town.
LATITUDE = 27.49
LONGITUDE = 77.67
ALTITUDE_M = 180
TIMEZONE = "Asia/Kolkata"

# CEEW "High frequency smart meter data from two districts in India" (Harvard Dataverse, CC0)
# https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/GOCHJH
CEEW_FILES = {
    "mathura2019.csv": "https://dataverse.harvard.edu/api/access/datafile/5425311",
    "mathura2021.csv": "https://dataverse.harvard.edu/api/access/datafile/5425312?format=original",
}

# Open-Meteo archive (ERA5 / IFS reanalysis). Radiation is the mean of the preceding hour.
WEATHER_START = "2019-05-01"
WEATHER_END = "2021-12-31"
WEATHER_VARS = [
    "shortwave_radiation",
    "direct_normal_irradiance",
    "diffuse_radiation",
    "temperature_2m",
    "cloud_cover",
    "wind_speed_10m",
]

NOMINAL_VOLTAGE_V = 230.0
VALID_VOLTAGE_RANGE_V = (150.0, 300.0)   # CEEW has outage zeros and spikes up to 654 V
MIN_METER_COVERAGE = 0.7                  # keep meters with >= 70% of 15-minute slots (outages count as missing)

# PV system assumptions (PM Surya Ghar subsidy tiers go up to 3 kW per home)
PV_KWP_PER_HOME = 3.0
PV_TILT_DEG = 25
PV_AZIMUTH_DEG = 180
PV_SYSTEM_LOSSES = 0.14
PV_GAMMA_PDC = -0.004

# Voltage bands live in engine/voltage_rules.json (engine.rules), each with its source.
