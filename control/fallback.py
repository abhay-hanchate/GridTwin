"""Fallback when the planned action fails at the observed step.

1. The first **safe** action in a finite permitted set (battery power levels the energy allows x uniform kept solar
   shares), every candidate solved in the real solver; preference: least curtailment, then least battery power.
2. If none is safe: the **least-violation** action of that set (smallest worst exceedance among converged solves),
   executed and labelled `unsafe_fallback`; never called safe.
3. If every candidate failed to solve: the idle battery with no curtailment, labelled `solver_failed`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from control.execution import Executor, StepInputs
from control.types import Action, BatteryModel, ControlState, Status
from control.verify import Check, physical_check
from engine.rules import VoltageRule

KEEP_LEVELS = (1.0, 0.75, 0.5, 0.25, 0.0)


@dataclass
class FallbackResult:
    action: Action
    status: Status
    check: Check                 # (1, 1) at the observed step for the chosen action
    tried: int
    safe_found: int
    reason: str


def candidates(state: ControlState, bat: BatteryModel, curtail: bool) -> list[Action]:
    up, down = bat.max_charge_kw(state.energy_kwh), bat.max_discharge_kw(state.energy_kwh)
    powers = sorted({0.0, up, up / 2, -down, -down / 2}, key=abs)
    keeps = KEEP_LEVELS if curtail else (1.0,)
    return [Action(battery_kw=float(p), keep=(k, k, k), topology_id=state.topology_id)
            for k in keeps for p in powers]


def search(ex: Executor, obs_now: StepInputs, state: ControlState, bat: BatteryModel, rule: VoltageRule, *,
           curtail: bool = True, vuf_limit: float | None = None) -> FallbackResult:
    cands = candidates(state, bat, curtail)
    n = len(cands)
    batch = obs_now.take([0] * n)                               # the same observed step, once per candidate
    res = ex.solve(batch, np.array([c.battery_kw for c in cands]), np.array([c.keep for c in cands]),
                   state.topology_id)
    chk = physical_check(res, rule, vuf_limit=vuf_limit)
    safe = np.flatnonzero(chk.safe[0])
    pick = lambda i: _one(chk, i)  # noqa: E731
    if len(safe):
        i = int(safe[0])                                         # candidates are ordered by preference
        a = cands[i]
        return FallbackResult(Action(a.battery_kw, a.keep, a.topology_id, "fallback_safe"), Status.VERIFIED_SAFE,
                              pick(i), n, len(safe), f"{len(safe)} of {n} permitted actions were safe")
    sev = chk.severity[0]
    if np.isfinite(sev).any():
        i = int(np.argmin(np.where(np.isfinite(sev), sev, np.inf)))
        a = cands[i]
        return FallbackResult(Action(a.battery_kw, a.keep, a.topology_id, "least_violation"), Status.UNSAFE_FALLBACK,
                              pick(i), n, 0, f"search exhausted: none of {n} permitted actions was safe; "
                              f"least violation {sev[i]:.2f} V-equivalent")
    idle = Action(0.0, (1.0, 1.0, 1.0), state.topology_id, "idle")
    i = next(j for j, c in enumerate(cands) if c.battery_kw == 0.0 and c.keep == (1.0, 1.0, 1.0))
    return FallbackResult(idle, Status.SOLVER_FAILED, pick(i), n, 0, f"none of {n} permitted actions solved")


def _one(chk: Check, i: int) -> Check:
    sl = (slice(0, 1), slice(i, i + 1))
    return Check(chk.safe[sl], chk.severity[sl], chk.v_max_v[sl], chk.v_min_v[sl], chk.line_max_pct[sl],
                 chk.trafo_pct[sl], chk.vuf_pct[sl], chk.margin_v[sl], [[chk.reasons[0][i]]])
