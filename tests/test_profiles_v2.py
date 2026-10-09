import numpy as np
import pandas as pd
import pytest

from engine import config, profiles

HEADER = "x_Timestamp,t_kWh,z_Avg Voltage (Volt),z_Avg Current (Amp),y_Freq (Hz),meter\n"


def _csv(tmp_path, rows):
    path = tmp_path / "x.csv"
    path.write_text(HEADER + "\n".join(rows) + "\n")
    return path


@pytest.fixture
def messy(tmp_path):
    return _csv(tmp_path, ["2019-05-01 00:00:00,0.02,240,1,50,A",
                           "2019-05-01 00:03:00,0.0,0,0,0,A",          # outage: zeros
                           "2019-05-01 00:06:00,0.9,654,1,50,A"])      # surge


def test_clean_marks_outage_and_surge_as_missing(messy):
    clean = profiles.read_ceew(messy)
    assert clean["v"].isna().tolist() == [False, True, True]
    assert clean["kwh"].isna().tolist() == [False, True, True]


def test_raw_keeps_every_reading(messy):
    raw = profiles.read_ceew_raw(messy)
    assert raw["v"].tolist() == [240.0, 0.0, 654.0]


def test_quality_report_counts_outages_and_surges(messy):
    rep = profiles.quality_report(profiles.read_ceew_raw(messy))
    assert rep["readings"] == 3 and rep["meters"] == 1
    assert rep["outage_share"] == pytest.approx(1 / 3, abs=1e-3) and rep["surge_share"] == pytest.approx(1 / 3, abs=1e-3)
    assert rep["max_voltage_v"] == 654.0
    assert rep["per_meter"]["A"]["valid"] == pytest.approx(1 / 3, abs=1e-3)


def _weather():
    idx = pd.date_range("2019-06-01 00:00", periods=24, freq="h")
    return pd.DataFrame({"direct_normal_irradiance": 600.0, "shortwave_radiation": 700.0,
                         "diffuse_radiation": 100.0, "temperature_2m": 30.0, "wind_speed_10m": 7.2}, index=idx)


def test_solar_output_depends_on_the_site():
    a = profiles.pv_hourly(_weather(), config.SITES["mathura"])
    b = profiles.pv_hourly(_weather(), config.SITES["bareilly"])
    assert a.max() > 0 and not np.allclose(a.to_numpy(), b.to_numpy())


def test_default_site_is_mathura():
    pd.testing.assert_series_equal(profiles.pv_hourly(_weather()), profiles.pv_hourly(_weather(), config.SITES["mathura"]))
