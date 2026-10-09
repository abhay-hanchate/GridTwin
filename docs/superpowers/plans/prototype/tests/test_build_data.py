import json

import numpy as np
import pandas as pd
import pytest

from engine import config
from engine.powerflow import day_inputs
from scripts import build_data


def _frames():
    idx = pd.date_range("2019-05-01", periods=480, freq="3min")          # one day of 3-minute readings
    return [pd.DataFrame({"ts": idx, "kwh": 0.02, "v": 240.0, "a": 1.0, "hz": 50.0, "meter": m})[["ts", "kwh", "v", "meter"]]
            for m in ("A", "B")]


def _weather():
    idx = pd.date_range("2019-05-01", periods=24, freq="h")
    return pd.DataFrame({"direct_normal_irradiance": 500.0, "shortwave_radiation": 600.0, "diffuse_radiation": 100.0,
                         "temperature_2m": 30.0, "wind_speed_10m": 7.2, "cloud_cover": 10.0}, index=idx)


def test_build_district_writes_every_output(tmp_path):
    report = build_data.build_district(_frames(), _weather(), config.SITES["mathura"], tmp_path, "mathura")
    for name in ("load_kw_mathura.parquet", "upstream_vm_pu_mathura.parquet", "weather_hourly_mathura.parquet",
                 "pv_kw_per_kwp_mathura.parquet", "quality_mathura.json"):
        assert (tmp_path / name).exists(), name
    assert report["meters"] == 2 and "coverage_by_year" in report
    loads = pd.read_parquet(tmp_path / "load_kw_mathura.parquet")
    assert list(loads.columns) == ["A", "B"]
    assert loads.iloc[0, 0] == pytest.approx(0.4)                         # 0.02 kWh per 3 min x 20 = 0.4 kW
    assert json.loads((tmp_path / "quality_mathura.json").read_text())["outage_share"] == 0.0


def test_day_inputs_reads_a_district_from_a_chosen_directory(tmp_path):
    build_data.build_district(_frames(), _weather(), config.SITES["mathura"], tmp_path, "mathura")
    di = day_inputs("2019-05-01", district="mathura", processed_dir=tmp_path)
    assert di.load_kw.shape == (96, 2)
    assert len(di.pv_kw_per_kwp) == 96 and len(di.upstream_vm_pu) == 96
    assert di.upstream_vm_pu.iloc[0] == pytest.approx(240.0 / 230.0, rel=1e-4)
