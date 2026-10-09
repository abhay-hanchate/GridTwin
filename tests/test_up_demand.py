import numpy as np
import pandas as pd
import pytest

from ml import up_demand


def _payload(days: dict[str, float], points: int = 480):
    """UPSLDC load-graph shape: one 3-minute series per date (HH:MM labels starting 00:01)."""
    times = [f"{(1 + 3 * i) // 60:02d}:{(1 + 3 * i) % 60:02d}" for i in range(points)]
    return {"category": times, "dataset": {d: [{"date": t, "demand": mw, "od": 0, "drawl": 0, "frequency": 50.0}
                                                 for t in times[: (points if mw > 0 else 0)]] for d, mw in days.items()}}


def test_parse_load_graph_gives_timestamped_megawatts():
    s = up_demand.parse_load_graph(_payload({"2026-10-08": 20000.0, "2026-10-09": 18000.0}))
    assert s.name == "demand_mw" and len(s) == 960
    assert s.index[0] == pd.Timestamp("2026-10-08 00:01") and s.iloc[-1] == 18000.0


def test_daily_energy_counts_only_complete_days():
    payload = _payload({"2026-10-08": 20000.0})
    payload["dataset"]["2026-10-09"] = payload["dataset"]["2026-10-08"][:231]       # today, half done
    e = up_demand.daily_energy(up_demand.parse_load_graph(payload))
    assert list(e.index) == [pd.Timestamp("2026-10-08")]
    assert e.iloc[0] == pytest.approx(480.0)                                        # 20,000 MW for 24 h = 480 MU


def test_up_ratio_is_yesterday_over_the_week_before():
    days = pd.date_range("2026-09-01", periods=10, freq="D")
    e = pd.Series([400.0] * 8 + [440.0, 500.0], index=days)
    r = up_demand.up_ratio(e)
    # for target day 2026-09-10: E(09-09) / mean(E(09-02 .. 09-08)) = 440 / 400
    assert r[pd.Timestamp("2026-09-10")] == pytest.approx(1.10)
    assert np.isnan(r[pd.Timestamp("2026-09-06")])                                  # only 4 of 7 days before
    assert pd.Timestamp("2026-09-11") in r.index                                    # usable for tomorrow


def test_up_ratio_tolerates_two_missing_days_but_not_three():
    days = pd.date_range("2026-09-01", periods=10, freq="D")
    e = pd.Series([400.0] * 9 + [440.0], index=days)                          # target day 09-11 uses E(09-10)
    two = e.drop([pd.Timestamp("2026-09-04"), pd.Timestamp("2026-09-06")])
    assert up_demand.up_ratio(two)[pd.Timestamp("2026-09-11")] == pytest.approx(1.10)
    three = two.drop(pd.Timestamp("2026-09-08"))
    assert np.isnan(up_demand.up_ratio(three)[pd.Timestamp("2026-09-11")])


def test_up_ratio_needs_yesterday():
    days = pd.date_range("2026-09-01", periods=10, freq="D")
    e = pd.Series([400.0] * 10, index=days).drop(pd.Timestamp("2026-09-09"))
    assert np.isnan(up_demand.up_ratio(e)[pd.Timestamp("2026-09-10")])


def test_history_averages_duplicate_dates(tmp_path):
    path = tmp_path / "met.csv"
    path.write_text("Date,Uttar Pradesh,Bihar\n2019-01-01,300,10\n2019-01-01,310,10\n2019-01-02,320,11\n")
    h = up_demand.load_history(path)
    assert h.tolist() == [305.0, 320.0] and h.index.freq == "D"


def test_record_merges_fetches_without_duplicates(tmp_path):
    path = tmp_path / "up.parquet"
    up_demand.record(_payload({"2026-10-08": 20000.0}), path)
    up_demand.record(_payload({"2026-10-08": 20000.0, "2026-10-09": 18000.0}), path)
    s = pd.read_parquet(path)["demand_mw"]
    assert len(s) == 960 and s.index.is_unique and s.index.is_monotonic_increasing


def test_combined_energy_prefers_the_live_record_where_both_exist():
    hist = pd.Series([300.0, 310.0], index=pd.date_range("2024-04-27", periods=2, freq="D"))
    live = pd.Series([450.0, 460.0], index=pd.date_range("2024-04-28", periods=2, freq="D"))
    both = up_demand.combined_energy(hist, live)
    assert both.tolist() == [300.0, 450.0, 460.0]          # 04-28 from the live record, 04-29 only live
