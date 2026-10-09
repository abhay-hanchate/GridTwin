"""F2: the evening report - one printable HTML page per street, date and rule, built from the /risk and /fixes results.

No external requests (inline CSS, no fonts or scripts), so it prints and works offline. It never prints meter ids:
homes are numbered positions on the modelled street. All sentences come from engine.explain, so every number is from
the result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from engine.explain import explain_risk, explain_verdict
from engine.rules import get_rule

TEMPLATES = Path(__file__).with_name("report_templates")
STRINGS = {
    "en": {"title": "Evening report: tomorrow on this street", "tomorrow": "Tomorrow", "by_hour": "Chance of unsafe voltage by hour",
           "thresholds": "Orange = watch (20% or more), red = act (50% or more).", "what_to_do": "What to do",
           "home": "Home", "from": "From phase", "to": "To phase", "limit_kw": "Lowest export limit (kW)", "when": "When it applies",
           "assumptions": "Where the numbers come from", "rule_source": "Voltage rule source",
           "footer": "GridTwin. Generated"},
    "hi": {"title": "शाम की रिपोर्ट: इस गली में कल", "tomorrow": "कल", "by_hour": "हर घंटे असुरक्षित वोल्टेज की संभावना",
           "thresholds": "नारंगी = सावधान (20% या अधिक), लाल = कार्रवाई (50% या अधिक)।", "what_to_do": "क्या करें",
           "home": "घर", "from": "पुराना फेज़", "to": "नया फेज़", "limit_kw": "न्यूनतम निर्यात सीमा (kW)", "when": "कब लागू",
           "assumptions": "आँकड़े कहाँ से आए", "rule_source": "वोल्टेज नियम का स्रोत", "footer": "GridTwin. बनाया गया"},
}


def _hourly(risk: dict) -> list[dict]:
    p, labels = risk["p_unsafe"], risk.get("t") or [f"{i // 4:02d}:{i % 4 * 15:02d}" for i in range(96)]
    watch, act = risk.get("thresholds", {}).get("watch", 0.2), risk.get("thresholds", {}).get("act", 0.5)
    out = []
    for h in range(24):
        peak = max(p[h * 4:(h + 1) * 4])
        out.append({"label": labels[h * 4][:2], "pct": round(peak * 100), "height": max(2, round(peak * 100)),
                    "level": "act" if peak >= act else "watch" if peak >= watch else "ok"})
    return out


def _limits(details: dict) -> list[dict]:
    lim = details.get("export_limits") or {}
    rows = []
    for home, kws in zip(lim.get("homes", []), lim.get("kw", [])):
        low = min(kws)
        steps = [t for t, k in zip(lim["t"], kws) if k <= low + 1e-6]
        rows.append({"home": home, "min_kw": round(low, 2), "when": f"{steps[0]}–{steps[-1]}" if steps else ""})
    return rows


def render_report(risk: dict, fixes: dict, lang: str = "en", network_label: str | None = None) -> str:
    if lang not in STRINGS:
        raise KeyError(f"no report strings for {lang!r}; available: {sorted(STRINGS)}")
    rule = get_rule(risk["rule"])
    focus = fixes["verdict"].get("recommended") or fixes["verdict"].get("closest")
    details = next((o.get("details") or {} for o in fixes["outcomes"] if o["id"] == focus), {})
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    return env.get_template("evening.html.j2").render(
        lang=lang, s=STRINGS[lang], title=STRINGS[lang]["title"], date=risk["date"],
        network_label=network_label or risk.get("network", ""), rule=rule.as_dict(), risk=risk,
        risk_text=explain_risk(risk, rule.vmax_v, lang), verdict_text=explain_verdict(fixes, lang),
        hourly=_hourly(risk), phase_moves=details.get("phase_moves", []), export_limits=_limits(details),
        provenance=risk.get("provenance", {}), generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
