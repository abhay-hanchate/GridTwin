"""State, action and record types of the controller. Energy is stored in kWh (unrounded); SoC is derived."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

STEP_H = 0.25


class Status(str, Enum):
    """What happened to one quarter hour. Only VERIFIED_SAFE may be called safe (docs/DECISIONS.md, Addition 1)."""
    VERIFIED_SAFE = "verified_safe"              # every declared check passed in the real solver at the observed step
    OPTIMISER_INFEASIBLE = "optimiser_infeasible"  # the linearised plan had no solution: not proof of impossibility
    SEARCH_EXHAUSTED = "search_exhausted"        # no permitted action in the finite fallback set was safe
    SOLVER_FAILED = "solver_failed"              # the physical solve did not converge for the executed action
    UNSAFE_FALLBACK = "unsafe_fallback"          # the least-violation permitted action, still unsafe
    INVALID_ACTION = "invalid_action"            # breaks a storage or equipment rule: never executed


@dataclass(frozen=True)
class BatteryModel:
    kw: float                       # charge and discharge rating
    kwh: float                      # usable capacity
    efficiency: float = 0.95        # each way: round trip is efficiency squared
    soc_min: float = 0.10
    soc_max: float = 0.90

    @property
    def round_trip(self) -> float:
        return self.efficiency ** 2

    @property
    def e_min(self) -> float:
        return self.kwh * self.soc_min

    @property
    def e_max(self) -> float:
        return self.kwh * self.soc_max

    def next_energy(self, energy_kwh: float, battery_kw: float) -> float:
        """Energy after one quarter hour at `battery_kw` (positive = charging)."""
        if battery_kw >= 0:
            return energy_kwh + STEP_H * battery_kw * self.efficiency
        return energy_kwh + STEP_H * battery_kw / self.efficiency

    def max_charge_kw(self, energy_kwh: float) -> float:
        return max(0.0, min(self.kw, (self.e_max - energy_kwh) / (STEP_H * self.efficiency)))

    def max_discharge_kw(self, energy_kwh: float) -> float:
        return max(0.0, min(self.kw, (energy_kwh - self.e_min) * self.efficiency / STEP_H))


@dataclass(frozen=True)
class SwitchPolicy:
    """Permitted switching: an explicit allowlist (hypothetical tie switches), a daily operation budget and a dwell."""
    allowed: tuple[str, ...] = ()
    max_operations: int = 2         # device operations per day; a reconfiguration is two (close the tie, open a line)
    dwell_steps: int = 8            # minimum quarter hours between reconfigurations


@dataclass(frozen=True)
class Action:
    battery_kw: float = 0.0                          # positive = charging
    keep: tuple[float, float, float] = (1.0, 1.0, 1.0)   # kept solar share per phase group (1 = no curtailment)
    topology_id: str = "base"
    source: str = "plan"                             # plan, fallback_safe, least_violation, idle


@dataclass(frozen=True)
class ControlState:
    energy_kwh: float
    topology_id: str = "base"
    operations_used: int = 0
    last_switch_step: int | None = None


def operations_for(current: str, target: str) -> int:
    """Device operations to move between topologies: 0 if unchanged, 2 per reconfiguration (close plus open)."""
    if current == target:
        return 0
    return 2 if "base" in (current, target) else 4


@dataclass
class StepRecord:
    """One executed quarter hour: the state-transition record required as evidence."""
    step: int
    time: str
    energy_before_kwh: float
    energy_after_kwh: float
    soc_before: float
    soc_after: float
    action: dict
    status: str
    reason: str
    replan_triggers: list[str]
    topology_before: str
    topology_after: str
    operations_used: int
    operations_left: int
    planner: dict                                   # status, rounds, trust region, prediction error, objective
    before: dict                                    # observed step, battery idle and no curtailment (same topology)
    after: dict                                     # observed step with the executed action
    forecast: dict                                  # issued forecast vs observation and the correction
    plan_horizon: list[dict] = field(default_factory=list)   # the full planned horizon at this step (battery, keep)
