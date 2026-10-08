"""D2, D7, D8: replay every candidate over the robust scenario set, rank the safe ones, give an honest verdict."""
from __future__ import annotations

from dataclasses import dataclass

from engine.fixes import catalog
from engine.fixes.base import Candidate, Outcome, evaluate_candidate
from engine.rules import VoltageRule
from engine.types import DayScenarioBatch, Network
from engine.verdict import build_verdict, shortfall


@dataclass
class TournamentResult:
    rule_id: str
    before: Outcome
    outcomes: list[Outcome]            # safe first (ranked), then the rest by remaining unsafe steps
    verdict: dict
    n_scenarios: int


def _as_result(o: Outcome) -> dict:
    return {"action_id": o.candidate.id, "label": o.candidate.label, "remaining_violation_steps": o.unsafe_steps,
            "cost": {"curtailed_kwh": o.summary["curtailed_kwh"]}, "binding_limit": o.binding_limit}


def run(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
        include_battery: bool = True, include_switching: bool = True, extra: list[Candidate] | None = None) -> TournamentResult:
    before = evaluate_candidate(Candidate("none", "Do nothing", "none", network), scn, rule, asymmetric=asymmetric)
    cands = catalog.build(network, scn, rule, asymmetric=asymmetric, include_battery=include_battery,
                          include_switching=include_switching) + list(extra or [])
    outcomes = [evaluate_candidate(c, scn, rule, asymmetric=asymmetric) for c in cands]
    safe = sorted((o for o in outcomes if o.acceptable), key=lambda o: o.cost)
    for rank, o in enumerate(safe, 1):
        o.rank = rank
    rest = sorted((o for o in outcomes if not o.acceptable), key=lambda o: (o.unsafe_steps, o.cost))
    results = [_as_result(o) for o in safe + rest]
    verdict = build_verdict(results, [r for r in results[:len(safe)]])
    if not verdict["safe_action_found"] and verdict["binding_limit"]:
        verdict["still_needs"] = shortfall(verdict["binding_limit"], rule, network)
    verdict["baseline_unsafe_steps"] = before.unsafe_steps
    return TournamentResult(rule.id, before, safe + rest, verdict, scn.shape[0])
