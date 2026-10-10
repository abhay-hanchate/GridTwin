"""F1: plain-language explanations built only from numbers in a computed result.

Templates (engine/explain_templates/<lang>.json) have {placeholders}; every value inserted comes from the risk, fix
or verdict dict passed in, so the text cannot state a number the engine did not produce. An optional rephrase
(GRIDTWIN_LLM_REPHRASE=1, any callable) is accepted only if it keeps exactly the same numbers; otherwise the
template text is used. The Hindi templates are a draft pending native-speaker review (see their _meta).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable

from engine.verdict import describe

TEMPLATES = Path(__file__).with_name("explain_templates")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


@lru_cache(maxsize=4)
def templates(lang: str) -> dict:
    path = TEMPLATES / f"{lang}.json"
    if not path.is_file():
        raise KeyError(f"no explanation templates for {lang!r}; available: {sorted(p.stem for p in TEMPLATES.glob('*.json'))}")
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def explain_risk(risk: dict, limit_v: float, lang: str = "en") -> str:
    """`limit_v` is the upper limit of the rule the risk was computed for, in volts."""
    t = templates(lang)
    hours = risk["expected_unsafe_hours"]
    # calibrated chances carry no scenario range (backend.v2.compute.shown_series), so the range is left out
    hours_range = "" if hours.get("p10") is None or hours.get("p90") is None else         t["hours_range"].format(p10=_fmt(hours["p10"]), p90=_fmt(hours["p90"]))
    values = {"first_act": risk.get("first_act"), "first_watch": risk.get("first_watch"),
              "hours": _fmt(hours["mean"]), "hours_range": hours_range,
              "peak_v": _fmt(risk["peak_voltage_v"]["p50"]), "limit_v": _fmt(limit_v),
              "watch_pct": _fmt(risk.get("thresholds", {}).get("watch", 0.2) * 100)}
    text = t[f"risk_{risk['level']}"].format(**values)
    if risk["level"] != "ok":
        applied = risk.get("calibration", {}).get("applied", False)
        text += " " + t["risk_calibrated" if applied else "risk_uncalibrated"]
    return text


def explain_fix(outcome: dict, lang: str = "en") -> str:
    t = templates(lang)
    text = t["fix_recommended"].format(label=outcome["label"], curtailed_kwh=_fmt(outcome["cost"]["curtailed_kwh"]),
                                       operations=outcome["cost"]["operations"])
    details = outcome.get("details") or {}
    if details.get("phase_moves"):
        text += " " + t["fix_phase_moves"].format(count=len(details["phase_moves"]))
    if details.get("export_limits", {}).get("homes"):
        text += " " + t["fix_export_limits"].format(count=len(details["export_limits"]["homes"]))
    return text


def explain_verdict(fixes: dict, lang: str = "en") -> str:
    """The recommendation, or the honest no-safe-action sentence naming the limit and what is still needed."""
    t, v = templates(lang), fixes["verdict"]
    by_id = {o["id"]: o for o in fixes["outcomes"]}
    if v["safe_action_found"]:
        return explain_fix(by_id[v["recommended"]], lang)
    closest = by_id[v["closest"]]
    text = t["verdict_no_safe"].format(closest_label=closest["label"], closest_steps=closest["unsafe_steps"],
                                       limit=describe(v["binding_limit"]) if v.get("binding_limit") else "-")
    if v.get("still_needs"):
        text += " " + t["verdict_still_needs"].format(still_needs=v["still_needs"])
    return text


def same_numbers(a: str, b: str) -> bool:
    return sorted(NUMBER.findall(a)) == sorted(NUMBER.findall(b))


def rephrase(text: str, llm: Callable[[str], str] | None = None) -> str:
    """Optional smoother wording; rejected unless every number survives unchanged."""
    if llm is None or os.getenv("GRIDTWIN_LLM_REPHRASE") != "1":
        return text
    try:
        candidate = llm(text)
    except Exception:
        return text
    return candidate if candidate and same_numbers(text, candidate) else text
