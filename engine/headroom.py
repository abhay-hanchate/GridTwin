"""E2, E3: how much more rooftop solar a node and phase can take, and the connection check built on it.

Method: add a probe rooftop system (following the scenarios' own solar shape) at a node and phase, and bisect its size
until the first failure on any scenario. Two criteria, because a street can already be unsafe without new solar:
  strict    zero unsafe steps in every scenario (0 kW when the street is already unsafe)
  no_worse  no step worsened against the street without the request (engine.violations.worsened_steps): a safe
            step stays safe and an unsafe one goes no further past its limit
Physics decides every answer: nothing here is learned.
"""
from __future__ import annotations

from dataclasses import replace

import networkx as nx
import numpy as np

from engine.inverters import VoltVarCurve
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch, Network
from engine.verdict import binding_limit_arrays
from engine.violations import evaluate, worsened_steps

PHASES = ("A", "B", "C")
# Flat state caps on rooftop solar as a share of the distribution transformer rating. Reported in the research
# document as [S] (search snippets): shown next to the physics, never as a finding.
FLAT_CAPS_PCT = {"Delhi": 20, "Rajasthan": 30, "Karnataka": 80, "Tamil Nadu": 90, "Odisha": 75}
NO_LIMIT_KW = 1e6


def electrical_distance(network: Network) -> dict[int, float]:
    g = nx.Graph()
    for a, b, length in zip(network.line_from, network.line_to, network.line_length_m):
        g.add_edge(int(a), int(b), weight=float(length))
    return nx.single_source_dijkstra_path_length(g, network.trafo.to_node, weight="weight")


def probe_nodes(network: Network) -> dict[str, int]:
    """Nearest and farthest home node from the transformer, by line length."""
    dist = electrical_distance(network)
    homes = sorted(set(int(n) for n in network.house_node), key=lambda n: dist[n])
    return {"near": homes[0], "far": homes[-1]}


def with_new_homes(network: Network, scn: DayScenarioBatch, node: int, phase: int, kwp: float, count: int = 1):
    """`count` new rooftop systems of `kwp` each at `node` on `phase`, with no demand of their own."""
    net = network.replace(house_node=np.r_[network.house_node, [node] * count],
                          house_phase=np.r_[network.house_phase, [phase] * count],
                          house_kwp=np.r_[network.house_kwp, [kwp] * count])
    s, t, _ = scn.load_kw.shape
    load = np.concatenate([scn.load_kw, np.zeros((s, t, count))], axis=2)
    return net, replace(scn, load_kw=load)


def _run(network, scn, rule, controls):
    res = DaySolver(network, asymmetric=True).solve(scn, controls)
    viol = evaluate(res, rule)
    return res, viol


def _bisect(ok, hi: float, tol: float) -> float:
    """Largest x in [0, hi] with ok(x), assuming ok is monotone (true, then false)."""
    if ok(hi):
        return hi
    if not ok(0.0):
        return 0.0
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def headroom(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, max_kw: float = 60.0,
             tol_kw: float = 0.5, controls: Controls = Controls()) -> dict:
    """Extra kW of rooftop solar per probe location and phase, under both criteria."""
    base_res, base = _run(network, scn, rule, controls)
    base_unsafe = int(base.unsafe.sum())
    out = {"rule": rule.id, "baseline_unsafe_steps": base_unsafe, "scenarios": scn.shape[0], "locations": {}}
    for where, node in probe_nodes(network).items():
        per_phase = {}
        for phase in range(3):
            def trial(kw, node=node, phase=phase):
                net, s = with_new_homes(network, scn, node, phase, kw)
                return _run(net, s, rule, controls)
            no_worse = _bisect(lambda kw: not worsened_steps(base_res, trial(kw)[0], rule).any(), max_kw, tol_kw)
            strict = _bisect(lambda kw: not trial(kw)[1].unsafe.any(), max_kw, tol_kw) if base_unsafe == 0 else 0.0
            net, s = with_new_homes(network, scn, node, phase, min(no_worse + tol_kw, max_kw))
            res, viol = _run(net, s, rule, controls)
            worst = int(viol.unsafe.sum(axis=1).argmax())
            per_phase[PHASES[phase]] = {"no_worse_kw": round(no_worse, 1), "strict_kw": round(strict, 1),
                                        "binding_limit": binding_limit_arrays(viol, res, rule, worst)
                                        if no_worse < max_kw else None}
        out["locations"][where] = {"node": node, "phases": per_phase}
    trafo_kva = network.trafo.sn_va / 1000
    installed = float(network.house_kwp.sum())
    out["installed_kw"] = round(installed, 1)
    out["flat_caps"] = {state: {"cap_pct": pct, "cap_kw": round(pct / 100 * trafo_kva, 1),
                                "installed_share_of_cap": round(installed / (pct / 100 * trafo_kva), 2),
                                "tag": "reported in search snippets, not verified"}
                        for state, pct in FLAT_CAPS_PCT.items()}
    return out


def check_connection(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, node: int, kw: float,
                     count: int = 1, phase: int | None = None, exempt_below_kw: float = 10.0,
                     tol_kw: float = 0.1) -> dict:
    """Approve, approve with conditions, or refuse `count` new systems of `kw` at `node` (best phase if not given).

    The test is "no worse": the request may not add unsafe steps. Conditions are tried cheapest first: standard
    Volt/VAR on the new inverters' street, then a day-ahead export limit on the new systems only.
    """
    if node not in set(int(n) for n in network.lv_nodes):
        raise ValueError(f"node {node} is not a low-voltage node of {network.name}")
    base_res, base = _run(network, scn, rule, Controls())
    base_unsafe = int(base.unsafe.sum())
    phases = [phase] if phase is not None else [0, 1, 2]

    def trial(ph, size, controls=Controls()):
        """(result, violations, number of steps the request worsens)."""
        net, s = with_new_homes(network, scn, node, ph, size, count)
        res, viol = _run(net, s, rule, controls)
        return res, viol, int(worsened_steps(base_res, res, rule).sum())

    tried = {ph: trial(ph, kw) for ph in phases}
    best = min(phases, key=lambda ph: (tried[ph][2], float(np.nanmax(tried[ph][0].u_pu))))
    # the condition tried below with Volt/VAR is judged against the same base street (no control)
    res, viol, worse = tried[best]
    out = {"node": node, "kw": kw, "count": count, "phase": PHASES[best], "rule": rule.id,
           "evidence": {"baseline_unsafe_steps": base_unsafe, "unsafe_steps_with_request": int(viol.unsafe.sum()),
                        "worsened_steps": worse,
                        "per_phase_worsened_steps": {PHASES[p]: tried[p][2] for p in phases}},
           "regulatory_status": (f"at or below {exempt_below_kw:g} kW: reported exempt from a technical feasibility "
                                 "study (unverified); this physics result is advisory") if kw <= exempt_below_kw else
                                "above the exemption threshold: feasibility study expected"}
    if worse == 0:
        return {**out, "decision": "approve", "conditions": [], "binding_limit": None}
    if trial(best, kw, Controls(volt_var=VoltVarCurve()))[2] == 0:
        return {**out, "decision": "approve_with_conditions", "binding_limit": None,
                "conditions": ["standard IEEE 1547 Volt/VAR on the street's inverters"]}
    n_old, t = network.n_homes, scn.shape[1]

    def limited(limit_kw):
        lim = np.full((t, n_old + count), NO_LIMIT_KW)
        lim[:, n_old:] = limit_kw
        return trial(best, kw, Controls(export_limit_kw=lim))[2] == 0
    limit = _bisect(limited, kw, tol_kw)
    if limit > 0:
        return {**out, "decision": "approve_with_conditions", "binding_limit": None,
                "conditions": [f"export limit of {limit:.1f} kW per new system"]}
    largest = _bisect(lambda size: trial(best, size)[2] == 0, kw, tol_kw)
    worst = int(viol.unsafe.sum(axis=1).argmax())
    return {**out, "decision": "refuse", "conditions": [], "largest_kw_that_passes": round(largest, 1),
            "binding_limit": binding_limit_arrays(viol, res, rule, worst)}


def cumulative_check(network: Network, scn: DayScenarioBatch, rule: VoltageRule, existing: list[dict],
                     new: dict) -> dict:
    """Small exempt systems add up: is the request safe alone, and together with those already connected?

    Both answers are judged against the street with none of these systems, so harm already done by earlier
    exempt connections is not hidden in the baseline.
    """
    base_res, base = _run(network, scn, rule, Controls())
    base_unsafe = int(base.unsafe.sum())
    phase = new.get("phase")
    alone = check_connection(network, scn, rule, node=new["node"], kw=new["kw"], phase=phase)
    net, s = network, scn
    for e in existing:
        net, s = with_new_homes(net, s, int(e["node"]), int(e["phase"]), float(e["kwp"]))
    ph = PHASES.index(alone["phase"])
    net, s = with_new_homes(net, s, int(new["node"]), ph, float(new["kw"]))
    res, viol = _run(net, s, rule, Controls())
    worse = int(worsened_steps(base_res, res, rule).sum())
    return {"baseline_unsafe_steps": base_unsafe, "existing_kw": round(sum(float(e["kwp"]) for e in existing), 1),
            "request_alone": alone["decision"], "phase": alone["phase"],
            "unsafe_steps_with_existing_and_request": int(viol.unsafe.sum()), "worsened_steps": worse,
            "safe_with_existing": worse == 0,
            "binding_limit": None if worse == 0 else
            binding_limit_arrays(viol, res, rule, int(viol.unsafe.sum(axis=1).argmax()))}
