import numpy as np
import pandas as pd

from backend.v2.settings import results_version
from scripts.nightly import SUNNY, demo_dates


def test_demo_dates_are_sunny_mixed_and_a_cloudy_monsoon_day():
    idx = pd.date_range("2025-01-01", "2025-12-31 23:00", freq="h")
    energy = pd.Series(np.linspace(1, 5, len(idx)), index=idx)
    energy[(idx >= "2025-07-20") & (idx < "2025-07-21")] = 0.01             # the cloudiest monsoon day
    dates = demo_dates(pd.DataFrame({"p50": energy}))
    assert dates["sunny"] == SUNNY and dates["cloudy"] == "2025-07-20"
    assert dates["mixed"] not in (SUNNY, "2025-07-20")


def test_results_version_ignores_line_endings(tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "backend" / "v2").mkdir(parents=True)
    (tmp_path / "backend" / "v2" / "compute.py").write_bytes(b"x = 1\n")
    (tmp_path / "engine" / "a.py").write_bytes(b"a = 1\n")
    unix = results_version(tmp_path)
    (tmp_path / "engine" / "a.py").write_bytes(b"a = 1\r\n")
    assert results_version(tmp_path) == unix
    (tmp_path / "engine" / "a.py").write_bytes(b"a = 2\n")
    assert results_version(tmp_path) != unix
