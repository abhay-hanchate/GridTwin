"""Honesty rules (plan 0.7 and P10.7): every number a user reads comes from results.json or an API response.

The UI and explanation strings may carry numbers only through {placeholders}; research claims tagged [S]
(single source) or [U] (unverified) never reach a user; hand-made sample data never reaches the built dashboard.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
I18N = sorted((ROOT / "frontend" / "src" / "i18n").glob("*.json"))
EXPLAIN = sorted((ROOT / "engine" / "explain_templates").glob("*.json"))
REPORT = ROOT / "engine" / "report_templates" / "evening.html.j2"
PLACEHOLDER = re.compile(r"\{[a-z0-9_]+\}")
DIGITS = re.compile(r"[0-9०-९]+")              # ASCII and Devanagari digits
# Definitions, not results: the 15-minute step and "8 of 10 cases" for the P10-P90 band.
DEFINITIONS = {"8", "10", "15"}
QUANTILE_LABEL = re.compile(r"\bP[159]0\b")


def strings(path: Path) -> dict[str, str]:
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if isinstance(v, str)}


def hard_coded_numbers(text: str) -> set[str]:
    return set(DIGITS.findall(QUANTILE_LABEL.sub("", PLACEHOLDER.sub("", text))))


def test_the_number_check_catches_a_hard_coded_result():
    assert hard_coded_numbers("Expect {hours} hours") == set()
    assert hard_coded_numbers("Expect 9.03 hours") == {"9", "03"}
    assert hard_coded_numbers("P10 to P90 range") == set()
    assert hard_coded_numbers("१२ घंटे") == {"१२"}


@pytest.mark.parametrize("path", I18N, ids=lambda p: p.name)
def test_dashboard_strings_carry_numbers_only_through_placeholders(path):
    bad = {k: v for k, v in strings(path).items() if hard_coded_numbers(v)}
    assert not bad, f"hard-coded numbers in {path.name}: {bad}"


@pytest.mark.parametrize("path", EXPLAIN, ids=lambda p: p.name)
def test_explanations_hard_code_only_definitions(path):
    bad = {k: sorted(n) for k, v in strings(path).items() if (n := hard_coded_numbers(v) - DEFINITIONS)}
    assert not bad, f"hard-coded numbers in {path.name}: {bad}"


def test_the_definitions_match_the_engine():
    # "15-minute": the steps the API serves
    index = json.loads((ROOT / "data" / "results" / "v2" / "index.json").read_text(encoding="utf-8"))
    key = next(e["key"] for e in index["entries"] if e["route"] == "risk")
    t = json.loads((ROOT / "data" / "results" / "v2" / f"{key}.json").read_text(encoding="utf-8"))["t"]
    assert len(t) == 96 and t[:2] == ["00:00", "00:15"]
    # "8 of 10 cases": the unsafe-hours range is the 10th to 90th percentile
    risk_source = (ROOT / "engine" / "risk.py").read_text(encoding="utf-8")
    assert "np.quantile(hours, 0.1)" in risk_source and "np.quantile(hours, 0.9)" in risk_source


def test_every_language_has_every_key():
    for group in (I18N, EXPLAIN):
        keys = [set(strings(p)) for p in group]
        assert all(k == keys[0] for k in keys), [p.name for p in group]


@pytest.mark.parametrize("path", [*I18N, *EXPLAIN, REPORT], ids=lambda p: p.name)
def test_no_single_source_or_unverified_research_claim_reaches_a_user(path):
    assert not re.search(r"\[(S|U)\]", path.read_text(encoding="utf-8"))


def test_hand_made_samples_are_test_inputs_only():
    src = ROOT / "frontend" / "src"
    shipped = [p for p in src.rglob("*.ts*") if ".test." not in p.name]
    leaks = [p.relative_to(ROOT).as_posix() for p in shipped if "fixtures/" in p.read_text(encoding="utf-8")]
    assert not leaks, f"production code imports sample data: {leaks}"
    for sample in (src / "fixtures" / "v2").glob("*_sample*.json"):
        assert "Tests only" in json.loads(sample.read_text(encoding="utf-8")).get("_note", ""), sample.name
