"""Voltage-rule library: every band the engine can check, with its source and verification status."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).with_name("voltage_rules.json")
ALIASES = {"10": "pm10", "6": "up_2005"}
VERIFICATION = {"primary", "secondary", "unverified"}


@dataclass(frozen=True)
class VoltageRule:
    id: str
    label: str
    vmin_pu: float
    vmax_pu: float
    nominal_v: float
    region: str
    source: str
    verification: str
    note: str = ""

    @property
    def vmin_v(self) -> float:
        return round(self.vmin_pu * self.nominal_v, 1)

    @property
    def vmax_v(self) -> float:
        return round(self.vmax_pu * self.nominal_v, 1)

    def as_dict(self) -> dict:
        return {**self.__dict__, "vmin_v": self.vmin_v, "vmax_v": self.vmax_v}


@lru_cache(maxsize=1)
def load_rules() -> dict[str, VoltageRule]:
    raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    rules: dict[str, VoltageRule] = {}
    for item in raw["rules"]:
        rule = VoltageRule(**item)
        if not 0.5 < rule.vmin_pu < 1.0 < rule.vmax_pu < 1.5:
            raise ValueError(f"rule {rule.id}: band must straddle 1.0 pu")
        if rule.verification not in VERIFICATION:
            raise ValueError(f"rule {rule.id}: verification must be one of {sorted(VERIFICATION)}")
        if not rule.source.strip():
            raise ValueError(f"rule {rule.id}: a source is required")
        rules[rule.id] = rule
    return rules


def get_rule(rule_id: str) -> VoltageRule:
    rules = load_rules()
    key = ALIASES.get(rule_id, rule_id)
    if key not in rules:
        raise KeyError(f"unknown voltage rule {rule_id!r}; valid ids: {sorted(rules)} and aliases {sorted(ALIASES)}")
    return rules[key]
