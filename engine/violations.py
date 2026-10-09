"""Array-based violation checks and day summaries (the vectorised counterpart of the legacy run_day)."""
from __future__ import annotations

import numpy as np

from engine.rules import VoltageRule
from engine.types import DayResult, Violations

STEP_H = 0.25
REVERSE_KW = 0.1


def evaluate(res: DayResult, rule: VoltageRule, *, vuf_limit: float | None = None) -> Violations:
    with np.errstate(invalid="ignore"):
        over = (res.u_pu > rule.vmax_pu).any(axis=(2, 3))
        under = (res.u_pu < rule.vmin_pu).any(axis=(2, 3))
        line = (res.line_loading_pct > 100).any(axis=2)
        trafo = res.trafo_loading_pct > 100
        unbalance = (res.vuf_pct > vuf_limit) if vuf_limit is not None else np.zeros_like(over)
    solver = ~res.converged
    unsafe = over | under | line | trafo | solver | unbalance
    return Violations(over=over, under=under, line=line, trafo=trafo, solver=solver, unbalance=unbalance,
                      unsafe=unsafe, rule_id=rule.id)


def summarise(res: DayResult, viol: Violations, s: int = 0) -> dict:
    """Headline numbers for scenario `s`, with the same keys as the legacy run_day summary where they exist."""
    ok = res.converged[s]
    u = res.u_pu[s][ok]
    pv_avail_kwh = float(res.pv_avail_kw[s].sum() * STEP_H)
    pv_kwh = float(res.pv_kw[s].sum() * STEP_H)
    return {
        "max_vm_pu": round(float(np.nanmax(u)), 4) if ok.any() else float("nan"),
        "min_vm_pu": round(float(np.nanmin(u)), 4) if ok.any() else float("nan"),
        "violation_steps": int(viol.unsafe[s].sum()),
        "solver_failed_steps": int((~ok).sum()),
        "reverse_flow_steps": int((res.trafo_p_kw[s][ok] < -REVERSE_KW).sum()),
        "max_trafo_loading_pct": round(float(np.nanmax(res.trafo_loading_pct[s][ok])), 1) if ok.any() else float("nan"),
        "max_line_loading_pct": round(float(np.nanmax(res.line_loading_pct[s][ok])), 1) if ok.any() else float("nan"),
        "reactive_loss_kvarh": round(float(np.nansum(res.q_loss_kvar[s]) * STEP_H), 2),
        "inverter_kvarh": round(float(np.clip(res.inverter_kvar[s], 0, None).sum() * STEP_H), 1),
        "pv_kwh": round(pv_kwh, 1),
        "curtailed_kwh": round(pv_avail_kwh - pv_kwh, 1),
        "losses_kwh": round(float(np.nansum(res.losses_kw[s]) * STEP_H), 2),
        "battery_throughput_kwh": round(float(np.abs(res.battery_kw[s]).sum() * STEP_H), 1),
        "max_vuf_pct": round(float(np.nanmax(res.vuf_pct[s][ok])), 2) if ok.any() else float("nan"),
        "max_neutral_a": round(float(np.nanmax(res.neutral_a[s][ok])), 1) if ok.any() else float("nan"),
    }


def exceedance(res: DayResult, rule: VoltageRule) -> dict[str, np.ndarray]:
    """How far each step is beyond its limits: voltage in volts (above or below the band), loading in points over 100%."""
    with np.errstate(invalid="ignore"):
        over = np.nanmax(res.u_pu - rule.vmax_pu, axis=(2, 3)) * rule.nominal_v
        under = np.nanmax(rule.vmin_pu - res.u_pu, axis=(2, 3)) * rule.nominal_v
        line = np.nanmax(res.line_loading_pct, axis=2) - 100
        trafo = res.trafo_loading_pct - 100
    clip = lambda a: np.nan_to_num(np.clip(a, 0, None), nan=0.0)  # noqa: E731
    return {"voltage_v": np.maximum(clip(over), clip(under)), "loading_pct": np.maximum(clip(line), clip(trafo))}


def worsened_steps(base: DayResult, new: DayResult, rule: VoltageRule, *, tol_v: float = 0.5,
                   tol_pct: float = 1.0) -> np.ndarray:
    """(S, T) steps that new solar makes worse than the base street: a safe step becomes unsafe, an unsafe step goes
    further past a limit (by more than tol_v volts or tol_pct loading points), or the solver fails where it did not.

    Counting only unsafe steps would miss harm on a street that is already unsafe (a strict rule saturates the count).
    """
    vb, vn = evaluate(base, rule), evaluate(new, rule)
    eb, en = exceedance(base, rule), exceedance(new, rule)
    newly = vn.unsafe & ~vb.unsafe
    deeper = vn.unsafe & ((en["voltage_v"] > eb["voltage_v"] + tol_v) | (en["loading_pct"] > eb["loading_pct"] + tol_pct))
    return newly | deeper | (vn.solver & ~vb.solver)
