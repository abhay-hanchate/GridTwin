"""A fix candidate, its verified outcome, and the lexicographic ranking."""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.fixes.battery import solve_with_battery
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network
from engine.verdict import binding_limit_arrays
from engine.violations import evaluate, summarise


@dataclass
class Candidate:
    id: str
    label: str
    kind: str                          # tap, inverter, combined, curtailment, envelope, phase, battery, switching
    network: Network
    controls: Controls = field(default_factory=Controls)
    operations: int = 0                # switch operations plus phase moves
    battery: BatterySpec | None = None
    params: dict = field(default_factory=dict)


@dataclass
class Outcome:
    candidate: Candidate
    summary: dict                      # headline numbers for the design (highest-solar) scenario
    unsafe_steps: int                  # worst case over the robust scenario set
    acceptable: bool
    binding_limit: dict | None
    cost: tuple
    rank: int | None = None


def margin_v(summary: dict, rule: VoltageRule) -> float:
    """Smallest distance (volts) between the day's voltage extremes and the rule band; bigger is safer."""
    return min(rule.vmax_pu - summary["max_vm_pu"], summary["min_vm_pu"] - rule.vmin_pu) * rule.nominal_v


def cost_vector(summary: dict, operations: int, rule: VoltageRule) -> tuple:
    """Lexicographic: least solar wasted, fewest operations, least battery use, then the LARGEST voltage margin
    (a robust choice), and only then the least wire loss."""
    return (round(summary["curtailed_kwh"], 1), operations, round(summary["battery_throughput_kwh"], 1),
            -round(margin_v(summary, rule), 1), round(summary["losses_kwh"], 2))


def evaluate_candidate(c: Candidate, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
                       design: int = -1) -> Outcome:
    """Replay every robust scenario; safe only if every scenario is safe at all steps and every solve converged."""
    if c.battery is not None:
        res = solve_with_battery(c.network, scn, c.battery, rule, c.controls, asymmetric=asymmetric)
    else:
        res = DaySolver(c.network, asymmetric=asymmetric).solve(scn, c.controls)
    viol = evaluate(res, rule)
    per_scn = viol.unsafe.sum(axis=1)
    worst = int(per_scn.argmax())
    s_design = design % scn.shape[0]
    summary = summarise(res, viol, s_design)
    return Outcome(candidate=c, summary=summary, unsafe_steps=int(per_scn.max()),
                   acceptable=bool(per_scn.max() == 0 and res.converged.all()),
                   binding_limit=binding_limit_arrays(viol, res, rule, worst),
                   cost=cost_vector(summary, c.operations, rule))
