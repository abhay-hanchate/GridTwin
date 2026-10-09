"""Enumerate the candidate fixes for one street and one robust scenario set."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from engine.fixes import switching
from engine.fixes.base import Candidate, evaluate_candidate
from engine.fixes.envelopes import compute_envelope
from engine.fixes.phase_assign import plan_phases
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network

BATTERY_SIZES_KW = (25, 50, 100, 150)
BATTERY_HOURS = (2, 4)
MAX_PHASE_MOVES_LIMITED = 15


def _design(scn: DayScenarioBatch) -> DayScenarioBatch:
    """The highest-solar scenario alone (the last one), used to design plans that are then verified on all."""
    return DayScenarioBatch(scn.t, scn.load_kw[-1:], scn.pv_per_kwp[-1:], scn.upstream_pu[-1:], scn.load_pf, scn.labels[-1:])


def worst_node(network: Network, scn: DayScenarioBatch, asymmetric: bool = True) -> int:
    res = DaySolver(network, asymmetric=asymmetric).solve(_design(scn))
    per_node = np.nanmax(res.u_pu[0], axis=(0, 2))
    return int(network.lv_nodes[int(per_node.argmax())])


def build(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
          include_battery: bool = True, include_switching: bool = True) -> list[Candidate]:
    vv, vw = VoltVarCurve(), VoltWattCurve()
    out: list[Candidate] = []
    add = lambda cid, label, kind, **kw: out.append(Candidate(cid, label, kind, kw.pop("network", network), **kw))  # noqa: E731

    add("tap_plus1", "Transformer tap +1 (off-load, seasonal)", "tap", controls=Controls(tap_pos=1), params={"tap_pos": 1})
    add("tap_plus2", "Transformer tap +2 (off-load, seasonal)", "tap", controls=Controls(tap_pos=2), params={"tap_pos": 2})
    add("volt_var", "Smart inverters: IEEE 1547 Volt/VAR", "inverter", controls=Controls(volt_var=vv))
    add("volt_watt", "Smart inverters: IEEE 1547 Volt/Watt", "inverter", controls=Controls(volt_watt=vw))
    add("volt_var_watt", "Smart inverters: Volt/VAR with Volt/Watt", "inverter", controls=Controls(volt_var=vv, volt_watt=vw))
    add("tap1_volt_var", "Tap +1 with IEEE 1547 Volt/VAR", "combined", controls=Controls(tap_pos=1, volt_var=vv))
    add("tap1_volt_var_watt", "Tap +1 with Volt/VAR and Volt/Watt", "combined", controls=Controls(tap_pos=1, volt_var=vv, volt_watt=vw))
    add("tap2_volt_var", "Tap +2 with IEEE 1547 Volt/VAR", "combined", controls=Controls(tap_pos=2, volt_var=vv), params={"tap_pos": 2})
    add("export_cap_80", "Solar export limited to 80% of output", "curtailment", controls=Controls(curtail_keep=0.8), params={"keep": 0.8})
    add("export_cap_60", "Solar export limited to 60% of output", "curtailment", controls=Controls(curtail_keep=0.6), params={"keep": 0.6})

    design = _design(scn)
    # Per-house export limits (operating envelope), alone and after the cheap settings.
    for cid, label, base in (("envelope", "Per-house export limits for tomorrow", Controls()),
                             ("tap1_volt_var_envelope", "Tap +1, Volt/VAR and per-house export limits", Controls(tap_pos=1, volt_var=vv))):
        env = compute_envelope(DaySolver(network, asymmetric=asymmetric), design, rule, base)
        add(cid, label, "envelope", controls=replace(base, export_limit_kw=env.limit_kw),
            params={"infeasible_steps": int(env.infeasible.sum())})

    # Phase reallocation of the homes, proposed by CP-SAT and verified like everything else.
    if asymmetric:
        net_kw = design.pv_per_kwp[0][:, None] * network.house_kwp[None, :] - design.load_kw[0]
        plan = plan_phases(net_kw, network.house_phase)
        few = plan_phases(net_kw, network.house_phase, max_moves=MAX_PHASE_MOVES_LIMITED)
        if few.moved > 0:
            add("phase_rebalance_limited", f"Re-balance phases, at most {MAX_PHASE_MOVES_LIMITED} homes move", "phase",
                network=network.with_phases(few.phases), operations=few.moved,
                params={"moved": few.moved, "imbalance_kw": [few.imbalance_before_kw, few.imbalance_after_kw]})
        if plan.moved > 0:
            net_p = network.with_phases(plan.phases)
            add("phase_rebalance", f"Re-balance phases ({plan.moved} homes move)", "phase", network=net_p, operations=plan.moved,
                params={"moved": plan.moved, "imbalance_kw": [plan.imbalance_before_kw, plan.imbalance_after_kw]})
            add("phase_tap1_volt_var", "Re-balance phases, tap +1 and Volt/VAR", "phase", network=net_p, operations=plan.moved,
                controls=Controls(tap_pos=1, volt_var=vv), params={"moved": plan.moved})

    if include_battery:
        node = worst_node(network, scn, asymmetric)
        for kw in BATTERY_SIZES_KW:
            for hours in BATTERY_HOURS:
                add(f"battery_{kw}kw_{hours}h", f"Community battery {kw} kW / {kw * hours} kWh at the worst node", "battery",
                    battery=BatterySpec(kw=float(kw), kwh=float(kw * hours), node=node), params={"kw": kw, "kwh": kw * hours})

    if include_switching:
        best = None
        for rec in switching.candidates(network):
            net_s = switching.apply(network, rec)
            if not net_s.is_radial():
                continue
            outcome = evaluate_candidate(Candidate("probe", "probe", "switching", net_s), scn, rule, asymmetric=asymmetric)
            key = (outcome.unsafe_steps, outcome.summary["max_vm_pu"])
            if best is None or key < best[0]:
                best = (key, rec, net_s)
        if best is not None:
            _, rec, net_s = best
            params = {"tie": list(rec.tie), "opened_line": rec.opened_line, "tie_length_m": round(rec.tie_length_m, 1)}
            add("switching", "Re-route a feeder through a tie switch", "switching", network=net_s, operations=rec.operations, params=params)
            add("switching_tap1_volt_var", "Tie switch, tap +1 and Volt/VAR", "switching", network=net_s, operations=rec.operations,
                controls=Controls(tap_pos=1, volt_var=vv), params=params)
    return out
