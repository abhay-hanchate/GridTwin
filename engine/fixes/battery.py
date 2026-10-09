"""D6: community battery with volt-droop control, solved step by step (the battery state couples the steps).

The battery is three pseudo-homes at its node (one per phase) whose 'load' is the charging power, so the same
batch solver is reused. Positive power = charging.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayResult, DayScenarioBatch, Network

STEP_H = 0.25
DISCHARGE_HOURS = range(18, 23)
DISCHARGE_MARGIN_PU = 0.03          # stay this far below the upper limit when discharging
LOW_MARGIN_PU = 0.03                # stay this far above the lower limit when charging
PROBE_KW = 10.0


def with_battery(network: Network, spec: BatterySpec) -> Network:
    return network.replace(house_node=np.r_[network.house_node, [spec.node] * 3],
                           house_phase=np.r_[network.house_phase, [0, 1, 2]],
                           house_kwp=np.r_[network.house_kwp, np.zeros(3)])


def node_sensitivity(solver: DaySolver, scn: DayScenarioBatch, n_homes: int) -> dict:
    """Voltage change (pu per kW) caused by the battery, measured with probe solves at the two steps that matter.

    On a weak overhead feeder one kW at the far end moves the voltage far more than a fixed droop constant assumes,
    and charging moves the lowest voltage (another node and phase) more than the highest. The probe runs at the step
    of the day's highest voltage and at the step of its lowest, using the first scenario:
      charge_max     fall of the highest voltage per kW charged (at the peak step)
      discharge_max  rise of the highest voltage per kW discharged (at the peak step)
      charge_min     fall of the lowest voltage per kW charged (at the lowest step)
    """
    zeros = np.zeros((1, scn.shape[1], 3))                                  # the battery's three pseudo-homes, idle
    first = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw[:1, :, :n_homes], zeros], axis=2), scn.pv_per_kwp[:1],
                             scn.upstream_pu[:1], scn.load_pf, scn.labels[:1])
    u0 = solver.solve(first).u_pu[0]                                       # (T, N, 3), battery at zero output
    peak_step, low_step = int(np.nanmax(u0, axis=(1, 2)).argmax()), int(np.nanmin(u0, axis=(1, 2)).argmin())

    def extremes(step: int, p_kw: float) -> tuple[float, float]:
        sl = slice(step, step + 1)
        load = np.concatenate([first.load_kw[:, sl, :n_homes], np.full((1, 1, 3), p_kw / 3)], axis=2)
        one = DayScenarioBatch(first.t[sl], load, first.pv_per_kwp[:, sl], first.upstream_pu[:, sl], first.load_pf, first.labels)
        u = solver.solve(one).u_pu
        return float(np.nanmax(u)), float(np.nanmin(u))

    (hi0, _), (hi_c, _), (hi_d, _) = extremes(peak_step, 0.0), extremes(peak_step, PROBE_KW), extremes(peak_step, -PROBE_KW)
    (_, lo0), (_, lo_c) = extremes(low_step, 0.0), extremes(low_step, PROBE_KW)
    floor = 1e-5
    return {"charge_max": max((hi0 - hi_c) / PROBE_KW, floor), "discharge_max": max((hi_d - hi0) / PROBE_KW, floor),
            "charge_min": max((lo0 - lo_c) / PROBE_KW, floor), "peak_step": peak_step, "low_step": low_step}


def solve_with_battery(network: Network, scn: DayScenarioBatch, spec: BatterySpec, rule: VoltageRule,
                       controls: Controls = Controls(), *, asymmetric: bool = True) -> DayResult:
    s, t = scn.shape
    n_h = network.n_homes
    solver = DaySolver(with_battery(network, spec), asymmetric=asymmetric)
    base = replace(controls, battery=None)
    soc = np.full(s, spec.soc_start)
    prev_vm, prev_min = np.ones(s), np.ones(s)
    parts, power = [], np.zeros((s, t))
    target = rule.vmax_pu - 0.02
    capacity = spec.kwh
    sens = node_sensitivity(solver, scn, n_h)                    # pu per kW at the battery node
    for i in range(t):
        room = (spec.soc_max - soc) * capacity / (STEP_H * spec.efficiency)
        avail = (soc - spec.soc_min) * capacity * spec.efficiency / STEP_H
        high = prev_vm > target
        # Charge only to bring the highest voltage back to the target, and never so hard that the voltage would fall
        # below the lower limit plus a margin (the feeder end is very sensitive, so the gain is the measured sensitivity).
        floor_kw = np.maximum(prev_min - (rule.vmin_pu + LOW_MARGIN_PU), 0) / sens["charge_min"]
        charge = np.minimum.reduce([np.full(s, spec.kw), room, (prev_vm - target) / sens["charge_max"], floor_kw])
        # Discharge in the evening only while there is headroom below the upper limit.
        headroom = np.maximum(rule.vmax_pu - DISCHARGE_MARGIN_PU - prev_vm, 0) / sens["discharge_max"]
        discharge = np.minimum.reduce([np.full(s, spec.kw / 2), avail, headroom])
        evening = ~high & (scn.t[i].hour in DISCHARGE_HOURS)
        p = np.where(high, charge, np.where(evening, -discharge, 0.0))
        soc = soc + np.where(p > 0, p * spec.efficiency, p / spec.efficiency) * STEP_H / capacity
        power[:, i] = p
        load = np.concatenate([scn.load_kw[:, i:i + 1, :], np.repeat((p / 3)[:, None, None], 3, axis=2)], axis=2)
        step = DayScenarioBatch(scn.t[i:i + 1], load, scn.pv_per_kwp[:, i:i + 1], scn.upstream_pu[:, i:i + 1], scn.load_pf, scn.labels)
        r = solver.solve(step, base)
        parts.append(r)
        prev_vm = np.nan_to_num(np.nanmax(r.u_pu[:, 0], axis=(1, 2)), nan=1.0)
        prev_min = np.nan_to_num(np.nanmin(r.u_pu[:, 0], axis=(1, 2)), nan=1.0)
    cat = lambda name: np.concatenate([getattr(r, name) for r in parts], axis=1)  # noqa: E731
    return DayResult(
        t=scn.t, u_pu=cat("u_pu"), line_loading_pct=cat("line_loading_pct"), trafo_loading_pct=cat("trafo_loading_pct"),
        trafo_p_kw=cat("trafo_p_kw"), losses_kw=cat("losses_kw"), q_loss_kvar=cat("q_loss_kvar"), pv_kw=cat("pv_kw"),
        pv_avail_kw=cat("pv_avail_kw"), inverter_kvar=cat("inverter_kvar"), battery_kw=power, neutral_a=cat("neutral_a"),
        vuf_pct=cat("vuf_pct"), converged=cat("converged"), passes=max(r.passes for r in parts))
