from engine import config


def _file(district, year):
    return next(f for f in config.CEEW_FILES if (f.district, f.year) == (district, year))


def test_ceew_files_cover_both_districts_and_three_years():
    keys = {(f.district, f.year) for f in config.CEEW_FILES}
    assert keys == {(d, y) for d in ("mathura", "bareilly") for y in (2019, 2020, 2021)}


def test_urls_use_original_format_only_for_ingested_tab_files():
    assert _file("mathura", 2019).url.endswith("/5425311") and "?" not in _file("mathura", 2019).url
    assert _file("mathura", 2021).url.endswith("/5425312?format=original")
    assert _file("bareilly", 2019).url.endswith("/5425325?format=original")
    assert _file("bareilly", 2020).filename == "ceew_bareilly_2020.csv"


def test_sites_and_legacy_constants():
    assert config.SITES["bareilly"].latitude == 28.37
    assert (config.LATITUDE, config.LONGITUDE, config.ALTITUDE_M) == (27.49, 77.67, 180)
    assert config.DISTRICTS == ("mathura", "bareilly")
