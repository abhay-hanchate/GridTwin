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


def test_planning_summary_keeps_headroom_per_location_and_phase_and_the_hosting_range():
    from scripts.nightly import planning_summary
    headroom = {"baseline_unsafe_steps": 3, "locations": {"near": {"node": 1, "phases": {"A": {"no_worse_kw": 4.5}}},
                                                          "far": {"node": 9, "phases": {"A": {"no_worse_kw": 1.0}}}}}
    hosting = {"without_fix": {"adoption_share": {"p10": 0.1, "p50": 0.2, "p90": 0.3}}, "with_volt_var": {}}
    out = planning_summary(headroom, hosting)
    assert out["headroom_kw"] == {"near": {"A": 4.5}, "far": {"A": 1.0}} and out["baseline_unsafe_steps"] == 3
    assert out["hosting_share"]["without_fix"]["p50"] == 0.2 and out["hosting_share"]["with_volt_var"] is None


def test_prune_keeps_only_the_files_the_index_names(tmp_path):
    from scripts.nightly import prune
    for name in ("risk_new", "risk_old", "fixes_old", "index"):
        (tmp_path / f"{name}.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("kept: not a cached result")
    removed = prune(tmp_path, [{"key": "risk_new"}])
    assert sorted(removed) == ["fixes_old.json", "risk_old.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index.json", "notes.txt", "risk_new.json"]
