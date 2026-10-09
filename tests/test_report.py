import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.jobs import cache_key
from backend.v2.settings import Settings
from engine.report import render_report

FIXTURES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "fixtures" / "v2"


def _load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def risk():
    r = _load("risk_sample")
    r["rule"] = "up_2005"
    return r


def test_report_carries_the_verdict_and_numbers_from_the_results(risk):
    fixes = _load("fixes_no_safe_sample")
    html = render_report(risk, fixes, "en")
    assert "No safe action" in html and "Uttar Pradesh" in html and "243.8" in html
    closest = next(o for o in fixes["outcomes"] if o["id"] == fixes["verdict"]["closest"])
    assert f"{closest['unsafe_steps']} unsafe" in html


def test_report_is_self_contained_and_prints_no_meter_ids(risk):
    html = render_report(risk, _load("fixes_safe_sample"), "en")
    assert not re.search(r"(src|href)=\"https?://", html) and "<script" not in html
    assert "@page" in html
    import pandas as pd
    from engine import config
    meter_ids = pd.read_parquet(config.PROCESSED_DIR / "load_kw.parquet").columns
    assert not any(str(m) in html for m in meter_ids if len(str(m)) > 3)      # real CEEW meter ids never appear


def test_report_lists_phase_moves_of_the_recommended_fix(risk):
    fixes = _load("fixes_safe_sample")
    rec = next(o for o in fixes["outcomes"] if o["id"] == fixes["verdict"]["recommended"])
    html = render_report(risk, fixes, "en")
    for move in rec.get("details", {}).get("phase_moves", []):
        assert f"<td>{move['home']}</td><td>{move['from']}</td><td>{move['to']}</td>" in html


def test_hindi_report_and_unknown_language(risk):
    assert "शाम की रिपोर्ट" in render_report(risk, _load("fixes_safe_sample"), "hi")
    with pytest.raises(KeyError):
        render_report(risk, _load("fixes_safe_sample"), "fr")


def test_report_route_serves_html_from_cached_results(tmp_path, risk):
    c = TestClient(create_app(Settings(code_version="r1", results_dir=tmp_path, offline=True)), raise_server_exceptions=False)
    assert c.get("/report", params={"date": "2025-05-15", "rule": "up_2005"}).status_code == 503
    (tmp_path / "v2").mkdir()
    params = {"date": "2025-05-15", "network": "benchmark_250", "rule": "up_2005"}
    (tmp_path / "v2" / f"{cache_key('risk', 'r1', **params, fix='none')}.json").write_text(json.dumps(risk))
    (tmp_path / "v2" / f"{cache_key('fixes', 'r1', **params)}.json").write_text(json.dumps(_load("fixes_no_safe_sample")))
    r = c.get("/report", params={"date": "2025-05-15", "rule": "up_2005"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "No safe action" in r.text
