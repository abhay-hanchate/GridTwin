from engine import config
from ml import solar_v2
from scripts import download_solar_v2 as dl


def test_request_asks_for_the_day_before_forecast_of_every_variable():
    p = dl.request_params(config.SITES["mathura"], "icon_global")
    assert p["models"] == "icon_global" and p["start_date"] == "2024-01-01" and p["end_date"] == "2025-12-31"
    assert p["hourly"].split(",") == [f"{v}_previous_day1" for v in config.WEATHER_VARS]
    assert "models" not in dl.request_params(config.SITES["mathura"], None)       # None = default best-match blend


def test_file_names_match_what_the_trainer_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    assert solar_v2.raw_path(None).name == "dayahead_mathura_2024_2025.json"             # Round 1 name is kept
    assert solar_v2.raw_path("ecmwf_ifs025").name == "dayahead_ecmwf_ifs025_mathura_2024_2025.json"


def test_an_existing_file_is_not_downloaded_again(tmp_path, monkeypatch):
    dest = tmp_path / "x.json"
    dest.write_text("x" * 2000)
    monkeypatch.setattr(dl.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert dl.fetch(config.SITES["mathura"], "icon_global", dest) is True
