import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_features", ROOT / "scripts" / "update_features.py")
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)


def test_features_csv_is_valid():
    rows = tracker.read_rows()
    assert list(rows[0].keys()) == tracker.COLUMNS
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert all(r["status"] in tracker.STATUSES for r in rows)
    # Done work records how it landed: a pull request, or a merge date for a branch merged directly.
    assert all(r["pull_request"] or r["merged_on"] for r in rows if r["status"] == "Done" and r["branch"] != "main")


def test_readme_table_matches_csv():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert tracker.render_table(tracker.read_rows()) in readme


def test_merge_marks_existing_branch_done_and_adds_new_ones():
    rows = [{"id": "F01", "feature": "A", "area": "", "owner": "P1", "branch": "feature/a",
             "status": "Planned", "pull_request": "", "merged_on": ""}]
    tracker.mark_done(rows, "feature/a", "12", "A", "me", "2026-09-29")
    assert rows[0]["status"] == "Done" and rows[0]["pull_request"] == "12"
    new = tracker.mark_done(rows, "fix/typo-in-map", "13", "Fix map label", "p4", "2026-09-29")
    assert new["id"] == "F02" and new["owner"] == "p4" and len(rows) == 2


def test_chore_branches_do_not_add_feature_rows():
    rows = [{"id": "F01", "feature": "A", "area": "", "owner": "P1", "branch": "feature/a",
             "status": "Planned", "pull_request": "", "merged_on": ""}]
    assert tracker.mark_done(rows, "chore/tracker-sync", "16", "Sync tracker", "p4", "2026-09-29") is None
    assert len(rows) == 1 and rows[0]["status"] == "Planned"


def test_merge_marks_multiple_features_delivered_by_one_branch():
    rows = [
        {"id": "F12", "feature": "Explain", "area": "ML", "owner": "P2", "branch": "person2",
         "status": "In progress", "pull_request": "", "merged_on": ""},
        {"id": "F13", "feature": "Warning", "area": "ML", "owner": "P2", "branch": "person2",
         "status": "In progress", "pull_request": "", "merged_on": ""},
    ]
    tracker.mark_done(rows, "person2", "12", "P2 delivery", "YASEER6974", "2026-09-29")
    assert all(row["status"] == "Done" and row["pull_request"] == "12" for row in rows)
