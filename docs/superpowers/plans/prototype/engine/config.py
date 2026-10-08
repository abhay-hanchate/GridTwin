"""Shared constants: location, data sources, file paths and grid limits."""
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CACHE_DIR = ROOT / "data" / "cache"


class Site(NamedTuple):
    latitude: float
    longitude: float
    altitude_m: float


SITES = {
    "mathura": Site(27.49, 77.67, 180),
    "bareilly": Site(28.37, 79.43, 270),     # city centre; altitude approximate, used only for sun position
}
DISTRICTS = tuple(SITES)

# Mathura is the original site; these names stay for code written before the second district.
LATITUDE, LONGITUDE, ALTITUDE_M = SITES["mathura"]
TIMEZONE = "Asia/Kolkata"


class CeewFile(NamedTuple):
    district: str
    year: int
    file_id: int
    original: bool = False      # some files are stored as ingested tab files; ?format=original returns the csv

    @property
    def filename(self) -> str:
        return f"ceew_{self.district}_{self.year}.csv"

    @property
    def url(self) -> str:
        base = f"https://dataverse.harvard.edu/api/access/datafile/{self.file_id}"
        return base + ("?format=original" if self.original else "")


# CEEW "High frequency smart meter data from two districts in India" (Harvard Dataverse, CC0)
# https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/GOCHJH
CEEW_FILES = [
    CeewFile("mathura", 2019, 5425311),
    CeewFile("mathura", 2020, 5425313),
    CeewFile("mathura", 2021, 5425312, original=True),
    CeewFile("bareilly", 2019, 5425325, original=True),
    CeewFile("bareilly", 2020, 5425310),
    CeewFile("bareilly", 2021, 5425314),
]

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

# Voltage bands now live in engine/voltage_rules.json (see engine/rules.py).
