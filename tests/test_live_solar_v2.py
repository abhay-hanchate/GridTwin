import json
import shutil
from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import config
from ml import live_solar_v2 as live
from ml import solar_v2
from ml.live_forecast import LiveForecastError

TARGET = date(2026, 10, 12)


def _payload(models=solar_v2.MODELS, scale=1.0, drop=None):
    times = pd.date_range(TARGET.isoformat(), periods=48, freq="h")
    hour = times.hour.to_numpy()
    sun = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)
    hourly = {"time": [t.isoformat() for t in times]}
    for i, m in enumerate(models):
        hourly[f"shortwave_radiation_{m}"] = list(sun * 800 * scale * (1 + 0.03 * i))
        hourly[f"direct_normal_irradiance_{m}"] = list(sun * 600)
        hourly[f"diffuse_radiation_{m}"] = list(sun * 120)
        hourly[f"temperature_2m_{m}"] = [30.0] * 48
        hourly[f"cloud_cover_{m}"] = [20.0] * 48
        hourly[f"wind_speed_10m_{m}"] = [6.0] * 48
    if drop:
        hourly[f"shortwave_radiation_{drop}"][5] = None
    return {"hourly": hourly}


@pytest.fixture()
def artifacts(tmp_path):
    """Frozen boosters trained on the real data if present; otherwise skip (they are committed with the repo)."""
    src = solar_v2.MODEL_DIR
    if not (src / "solar_v2_manifest.json").exists():
        pytest.skip("run python -m ml.solar_v2 first")
    for f in src.glob("solar_v2_*"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def test_request_asks_for_all_models_in_one_call():
    p = live.request_params(TARGET)
    assert p["models"] == ",".join(solar_v2.MODELS) and p["start_date"] == "2026-10-12" and p["end_date"] == "2026-10-13"


def test_models_with_gaps_are_left_out_and_too_few_models_is_an_error():
    assert len(live.frames_from_payload(_payload(drop="gfs_global"), TARGET)) == 4
    with pytest.raises(LiveForecastError, match="need 3"):
        live.frames_from_payload(_payload(models=solar_v2.MODELS[:2]), TARGET)
    with pytest.raises(LiveForecastError, match="no valid hourly table"):
        live.frames_from_payload({}, TARGET)


def test_frozen_models_give_96_ordered_intervals_and_a_stated_width_source(artifacts, tmp_path):
    frames = live.frames_from_payload(_payload(), TARGET)
    fc, source = live.predict_live(frames, TARGET, artifacts, tmp_path / "missing.json")
    assert len(fc) == 96 and list(fc.columns) == ["p10", "p50", "p90"]
    assert (fc.p10 <= fc.p50).all() and (fc.p50 <= fc.p90).all() and fc.min().min() >= 0 and fc.max().max() <= 1
    assert fc.loc[fc.index.hour == 12, "p50"].max() > 0.3 and fc.loc[fc.index.hour == 2, "p50"].max() == 0
    assert source.startswith("manifest value")


def test_monitor_state_overrides_the_manifest_width(artifacts, tmp_path):
    state = tmp_path / "state.json"
    frames = live.frames_from_payload(_payload(), TARGET)
    narrow, _ = live.predict_live(frames, TARGET, artifacts, tmp_path / "none.json")
    state.write_text(json.dumps({"q": 0.2, "as_of": "2026-10-11"}))
    wide, source = live.predict_live(frames, TARGET, artifacts, state)
    assert source == "monitor state from 2026-10-11" and (wide.p90 - wide.p10).sum() > (narrow.p90 - narrow.p10).sum()
    assert np.allclose(wide.p50, narrow.p50)


def test_a_tampered_model_file_is_rejected(artifacts, tmp_path):
    (artifacts / "solar_v2_p50.txt").write_text("tampered")
    with pytest.raises(LiveForecastError, match="checksum mismatch"):
        live.predict_live(live.frames_from_payload(_payload(), TARGET), TARGET, artifacts, tmp_path / "none.json")


def test_missing_manifest_is_a_clean_error(tmp_path):
    with pytest.raises(LiveForecastError, match="manifest"):
        live.predict_live(live.frames_from_payload(_payload(), TARGET), TARGET, tmp_path, tmp_path / "none.json")


def test_end_to_end_wiring_with_the_network_and_inference_stubbed(monkeypatch):
    stub = pd.DataFrame({"p10": 0.1, "p50": 0.2, "p90": 0.3}, index=pd.date_range("2026-10-12", periods=96, freq="15min"))
    monkeypatch.setattr(live, "fetch_payload", lambda target, site=None: _payload())
    monkeypatch.setattr(live, "predict_live", lambda frames, target, **kw: (stub, "stub"))
    r = live.live_solar_forecast_v2(TARGET)
    assert len(r["points"]) == 96 and r["interval_source"] == "stub" and r["nwp_models"] == sorted(solar_v2.MODELS)
    assert r["provenance"].startswith("modeled") and r["points"][0] == {"t": "00:00", "p10": 0.1, "p50": 0.2, "p90": 0.3}


def test_the_target_days_season_picks_the_manifest_width(artifacts, tmp_path):
    manifest_path = artifacts / "solar_v2_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["conformal_q_by_season"] = {"winter": 0.0, "summer": 0.0, "monsoon": 0.0, "post_monsoon": 0.3}
    manifest_path.write_text(json.dumps(manifest))
    frames = live.frames_from_payload(_payload(), TARGET)                  # 12 October: post-monsoon
    fc, source = live.predict_live(frames, TARGET, artifacts, tmp_path / "none.json")
    assert source.startswith("manifest value") and "post_monsoon" in source
    noon = fc.index.hour == 12
    assert (fc.loc[noon, "p90"] - fc.loc[noon, "p50"]).min() > 0.25


def test_monitor_state_per_season_overrides_everything(artifacts, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"q": 0.0, "q_by_season": {"post_monsoon": 0.2}, "as_of": "2026-10-11"}))
    frames = live.frames_from_payload(_payload(), TARGET)
    _, source = live.predict_live(frames, TARGET, artifacts, state)
    assert source == "monitor state for post_monsoon from 2026-10-11"
