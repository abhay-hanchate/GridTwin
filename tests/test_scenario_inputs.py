"""The inputs the live scenario generator draws from: every day of the year must have a grid-voltage history, and the
generated grid voltage must follow the real record month by month (a sanity check against the data, not a forecast
skill claim). Found by looking at midnight voltages that were identical across dates, and March that was 8 V off."""
import numpy as np
import pandas as pd
import pytest

from backend.v2 import compute

history = pytest.importorskip("backend.v2.compute")._history_files


def test_yesterdays_grid_voltage_exists_for_every_day_of_the_year():
    _, _, up, source = history()
    assert source == "full", "data/processed/v2 Mathura files are missing: March and April have no voltage history without them"
    for d in pd.date_range("2025-01-01", "2025-12-31"):
        mean = compute.yesterday_upstream_mean(d, up)
        assert np.isfinite(mean) and 0.9 < mean < 1.2, d.date()


def test_the_proxy_year_is_the_first_with_data():
    _, _, up, _ = history()
    # March has no 2019 record (it starts in May) but has 2020; August has 2019.
    mar = compute.yesterday_upstream_mean(pd.Timestamp("2025-03-15"), up)
    real_2020 = up.loc["2020-03-14":"2020-03-14 23:45"].mean()
    assert mar == pytest.approx(float(real_2020))
    aug = compute.yesterday_upstream_mean(pd.Timestamp("2025-08-15"), up)
    assert aug == pytest.approx(float(up.loc["2019-08-14":"2019-08-14 23:45"].mean()))


@pytest.mark.parametrize("month", [3, 4, 12])
def test_generated_grid_voltage_follows_the_real_record_in_the_months_that_were_wrong_or_matter(month):
    net = compute.network("benchmark_250")
    _, _, up, _ = history()
    scn = compute.scenarios(f"2025-{month:02d}-15", net, n=30)
    model = scn.upstream_pu * 230
    real = (up[up.index.month == month].dropna()) * 230
    assert abs(float(model.mean()) - float(real.mean())) < 6.0                 # volts
    by_hour_real = real.groupby(real.index.hour).mean().to_numpy()
    by_hour_model = pd.Series(model.mean(axis=0)).groupby(np.arange(96) // 4).mean().to_numpy()
    assert np.corrcoef(by_hour_real, by_hour_model)[0, 1] > 0.85               # the shape of the day, midnight to midnight
