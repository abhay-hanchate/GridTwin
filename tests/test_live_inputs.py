import sys
import types
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.v2 import live_inputs


def _points(value):
    return [{"t": f"{i // 4:02d}:{i % 4 * 15:02d}", "p10": value * 0.9, "p50": value, "p90": value * 1.1} for i in range(96)]


@pytest.fixture
def fake_ml(monkeypatch):
    solar = pd.DataFrame({"p10": 0.1, "p50": 0.2, "p90": 0.3}, index=pd.date_range("2030-01-02", periods=96, freq="15min"))
    live_solar_v2 = types.SimpleNamespace(fetch_payload=lambda target: {}, frames_from_payload=lambda p, t: {},
                                          predict_live=lambda frames, target: (solar, "monitor state for winter"))
    def no_anchor(target):
        raise FileNotFoundError("data/raw/zenodo_state_demand/...")
    live_dayahead = types.SimpleNamespace(current_ratio=no_anchor, live_forecast=lambda district, target, ratio=None: {
        "anchor": {"note": "pattern only"}, "demand": {"model": "pattern_only", "points": _points(0.5)},
        "voltage": {"model": "pattern_only", "points": _points(241.5)}})
    ml = types.ModuleType("ml")
    ml.live_solar_v2, ml.live_dayahead = live_solar_v2, live_dayahead
    monkeypatch.setitem(sys.modules, "ml", ml)
    monkeypatch.setitem(sys.modules, "ml.live_solar_v2", live_solar_v2)
    monkeypatch.setitem(sys.modules, "ml.live_dayahead", live_dayahead)


def test_live_forecasts_return_96_rows_and_voltage_in_per_unit(fake_ml):
    f = live_inputs.live_forecasts("2030-01-02")
    assert all(len(f[k]) == 96 for k in ("solar", "demand", "voltage_pu"))
    assert f["voltage_pu"]["p50"].iloc[0] == pytest.approx(241.5 / 230)
    assert f["demand"]["p90"].iloc[0] == pytest.approx(0.55)
    assert "pattern_only" in f["provenance"]["voltage"] and "winter" in f["provenance"]["solar"]


def test_only_today_and_later_are_live(monkeypatch):
    monkeypatch.setattr(live_inputs, "today_ist", lambda: date(2026, 10, 9))
    assert live_inputs.is_live("2026-10-10") and live_inputs.is_live("2026-10-09")
    assert not live_inputs.is_live("2025-05-15")


def test_a_short_forecast_is_rejected():
    with pytest.raises(ValueError, match="96"):
        live_inputs._frame(_points(1.0)[:48])


def test_live_dates_use_the_live_forecasts_and_their_provenance(monkeypatch):
    from backend.v2 import compute
    flat = pd.DataFrame({"p10": 0.0, "p50": 0.0, "p90": 0.0}, index=range(96))
    fake = {"solar": flat, "demand": flat + 0.4, "voltage_pu": flat + 1.07,
            "provenance": {"voltage": "modeled: live day-ahead grid voltage (pattern_only)"}}
    monkeypatch.setattr(live_inputs, "is_live", lambda d: d == "2030-01-02")
    monkeypatch.setattr(compute, "_live", lambda d: fake)
    net = compute.network("benchmark_250")
    scn = compute.scenarios("2030-01-02", net, n=5)
    assert np.allclose(scn.upstream_pu, 1.07) and np.allclose(scn.pv_per_kwp, 0.0)
    assert "pattern_only" in compute.provenance("2030-01-02")["voltage"]
    assert compute.provenance("2025-05-15") == compute.PROVENANCE           # demo dates are unchanged
