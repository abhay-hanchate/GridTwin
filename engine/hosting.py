"""E1: probabilistic hosting capacity.

Which homes adopt rooftop solar, how big their systems are and which phase they sit on are unknown, and they change
the answer. Each Monte Carlo draw fixes a random adoption order, a size per home (from `kw_tiers`) and a random phase
per home. The draw's capacity is the highest adoption level at which the street does no worse than the same homes
and phases with no solar (no worsened step: engine.violations.worsened_steps), found by binary search over the levels
(failures are assumed monotone in adoption). P10/P50/P90 over the draws are reported, with the binding limit seen
most often at the first failing level.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch, Network
from engine.verdict import binding_limit_arrays
from engine.violations import evaluate, worsened_steps


def hosting_capacity(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, levels=None,
                     kw_tiers: tuple = (1.0, 3.0, 5.0), draws: int = 50, seed: int = 42,
                     controls: Controls = Controls()) -> dict:
    if draws < 1:
        raise ValueError("need at least one Monte Carlo draw")
    levels = np.linspace(0, 1, 11) if levels is None else np.asarray(levels, float)
    rng = np.random.default_rng(seed)
    n = network.n_homes

    def unsafe(net):
        res = DaySolver(net, asymmetric=True).solve(scn, controls)
        return res, evaluate(res, rule)

    capacity, capacity_kw, failing = [], [], Counter()
    for _ in range(draws):
        order = rng.permutation(n)
        size = rng.choice(kw_tiers, n)
        phase = rng.integers(0, 3, n)
        net_draw = network.with_phases(phase)
        cache: dict[int, tuple] = {}

        def run(i: int):
            if i not in cache:
                k = int(round(levels[i] * n))
                kwp = np.zeros(n)
                kwp[order[:k]] = size[order[:k]]
                cache[i] = (*unsafe(net_draw.with_pv(kwp)), float(kwp.sum()))
            return cache[i]
        base = run(0)[0]                                   # the same draw's homes and phases with no solar

        def ok(i: int) -> bool:
            return not worsened_steps(base, run(i)[0], rule).any()
        # Binary search for the last passing level (failures are assumed monotone in adoption, as in headroom).
        lo, hi = 0, len(levels) - 1
        if ok(hi):
            lo = hi
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        capacity.append(float(levels[lo]))
        capacity_kw.append(run(lo)[2])
        if lo < len(levels) - 1:
            res, viol, _ = run(lo + 1)
            limit = binding_limit_arrays(viol, res, rule, int(viol.unsafe.sum(axis=1).argmax()))
            failing[limit["type"] if limit else "unknown"] += 1
    capacity_arr = np.array(capacity)
    failures_at = np.array([(capacity_arr < lv - 1e-9).sum() for lv in levels])
    q = lambda a, p: round(float(np.quantile(a, p)), 3)  # noqa: E731
    return {
        "rule": rule.id, "draws": draws, "seed": seed, "homes": n, "kw_tiers": list(kw_tiers),
        "criterion": "no step worsened against the same homes and phases with no solar (engine.violations.worsened_steps)",
        "adoption_share": {"p10": q(capacity, 0.1), "p50": q(capacity, 0.5), "p90": q(capacity, 0.9)},
        "installed_kw": {"p10": round(q(capacity_kw, 0.1), 1), "p50": round(q(capacity_kw, 0.5), 1),
                         "p90": round(q(capacity_kw, 0.9), 1)},
        "share_of_draws_failed_by_level": {f"{lv:.1f}": round(float(f / draws), 3) for lv, f in zip(levels, failures_at)},
        "binding": failing.most_common(1)[0][0] if failing else None,
    }
