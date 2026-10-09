"""D3: choose the phase of each (movable) home so net injections are balanced at the critical steps.

CP-SAT minimises the largest difference between phase net-injections over the critical steps; the result is
only a proposal, and the tournament verifies it with the full power flow.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model

SCALE = 100          # kW to integer units of 0.01 kW


@dataclass
class PhasePlan:
    phases: np.ndarray            # (H,) proposed phase per home
    moved: int                    # homes whose phase changed
    imbalance_before_kw: float    # largest phase difference over critical steps
    imbalance_after_kw: float
    status: str


def critical_steps(net_kw: np.ndarray, k: int = 6) -> np.ndarray:
    """Steps with the largest total export and the largest total import (net_kw is (T, H), export positive)."""
    total = net_kw.sum(axis=1)
    return np.unique(np.r_[np.argsort(total)[-k:], np.argsort(total)[:k]])


def _imbalance(phases: np.ndarray, net_kw: np.ndarray, steps: np.ndarray) -> float:
    per_phase = np.stack([net_kw[steps][:, phases == p].sum(axis=1) for p in range(3)], axis=1)
    return float((per_phase.max(axis=1) - per_phase.min(axis=1)).max())


def plan_phases(net_kw: np.ndarray, current: np.ndarray, movable: np.ndarray | None = None,
                max_moves: int | None = None, time_limit_s: float = 20.0, workers: int = 1) -> PhasePlan:
    """net_kw: (T, H) net injection per home (PV minus load). movable: (H,) bool; max_moves: cap on changes."""
    n_h = net_kw.shape[1]
    movable = np.ones(n_h, dtype=bool) if movable is None else np.asarray(movable, dtype=bool)
    steps = critical_steps(net_kw)
    ints = np.rint(net_kw[steps] * SCALE).astype(int)                         # (K, H)

    m = cp_model.CpModel()
    x = [[m.NewBoolVar(f"x{h}_{p}") for p in range(3)] for h in range(n_h)]
    for h in range(n_h):
        m.AddExactlyOne(x[h])
        if not movable[h]:
            m.Add(x[h][int(current[h])] == 1)
    bound = int(np.abs(ints).sum(axis=1).max()) + 1
    z = m.NewIntVar(0, 2 * bound, "z")
    for k in range(len(steps)):
        load = [sum(int(ints[k, h]) * x[h][p] for h in range(n_h)) for p in range(3)]
        for a in range(3):
            for b in range(a + 1, 3):
                m.Add(load[a] - load[b] <= z)
                m.Add(load[b] - load[a] <= z)
    if max_moves is not None:
        stay = [x[h][int(current[h])] for h in range(n_h) if movable[h]]
        m.Add(sum(stay) >= len(stay) - max_moves)
    m.Minimize(z)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers          # 1 = reproducible; more is faster but not deterministic
    solver.parameters.random_seed = 42
    status = solver.Solve(m)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PhasePlan(current.copy(), 0, _imbalance(current, net_kw, steps), _imbalance(current, net_kw, steps), name)
    phases = np.array([[solver.Value(x[h][p]) for p in range(3)].index(1) for h in range(n_h)])
    return PhasePlan(phases, int((phases != current).sum()), _imbalance(current, net_kw, steps),
                     _imbalance(phases, net_kw, steps), name)
