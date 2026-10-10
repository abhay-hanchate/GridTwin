"""Multi-step planner: sequential linear programming over the horizon, every round checked in the real solver.

Each round:
1. Linearise every phase voltage, line loading and the transformer loading of every retained scenario and step around
   the current reference trajectory, by central finite differences of the four actuators (battery power and the
   kept solar share of the three phase groups) in the real three-phase solver. Steps are independent power flows, so
   one perturbed solve gives the derivative of every step at once: nine solves per round.
2. Solve a MILP (HiGHS) over the horizon: charge and discharge power with a binary that forbids both at once, the
   battery's energy recursion and limits, the kept solar shares, a trust region around the reference, and every
   linearised limit with a margin. Each (scenario, step, kind) has one slack, heavily penalised, so a horizon that
   cannot be made safe still returns the least-violation plan and names the steps that need the slack.
3. Replay the plan in the real solver. A plan is `verified` only when every retained scenario and step passes every
   declared check. Otherwise the reference moves to the plan and the trust region halves where the linear model
   missed. At most `rounds` rounds; the best physically checked plan is returned.

The same plan applies to every retained scenario (non-anticipative open-loop plan); only its first action is executed
before the controller replans (control.replay).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from control.execution import N_GROUPS, Executor, StepInputs
from control.types import STEP_H, BatteryModel, ControlState
from control.verify import NOMINAL_V, Check, physical_check
from engine.rules import VoltageRule


@dataclass(frozen=True)
class PlannerConfig:
    curtail: bool = True                 # False: battery only (the like-for-like comparison with the reactive rule)
    margin_v: float = 1.0                # volts kept clear of each voltage limit in the linear model
    margin_loading: float = 2.0          # percentage points kept clear of 100% loading
    trust_kw: float = 15.0               # first trust region on battery power
    trust_keep: float = 0.5              # first trust region on each kept solar share
    rounds: int = 4
    probe_kw: float = 2.0                # finite-difference steps
    probe_keep: float = 0.1
    w_curtail: float = 1.0               # per kWh of solar curtailed
    w_throughput: float = 0.02           # per kWh moved through the battery
    w_reserve: float = 0.05              # per kWh below the end-of-horizon energy target
    reserve_soc: float = 0.5             # soft target at the end of the horizon (never a hard limit)
    w_slack: float = 200.0               # per volt-equivalent of a limit the plan cannot meet
    vuf_limit: float | None = None
    time_limit_s: float = 10.0


@dataclass
class PlanResult:
    battery_kw: np.ndarray               # (H,) positive = charging
    charge_kw: np.ndarray
    discharge_kw: np.ndarray
    keep: np.ndarray                     # (H, 3)
    energy_kwh: np.ndarray               # (H+1,) planned trajectory, starting with the actual energy
    verified: bool
    check: Check                         # physical check of the returned plan, every retained scenario and step
    status: str                          # verified_safe, horizon_unsafe or optimiser_infeasible
    predicted_infeasible_steps: list[int]
    curtailed_kwh: float
    rounds: list[dict] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def horizon(self) -> int:
        return len(self.battery_kw)

    def summary(self) -> dict:
        return {"status": self.status, "verified": self.verified, "rounds": self.rounds,
                "predicted_infeasible_steps": self.predicted_infeasible_steps,
                "curtailed_kwh": round(self.curtailed_kwh, 3), "seconds": round(self.seconds, 3)}


def _outputs(res) -> dict[str, np.ndarray]:
    """Monitored outputs, each (S, T, M): every phase voltage in volts, every line loading, the transformer loading."""
    s, t = res.trafo_loading_pct.shape
    return {"v": (res.u_pu * NOMINAL_V).reshape(s, t, -1), "line": res.line_loading_pct,
            "trafo": res.trafo_loading_pct[:, :, None]}


def _linearise(ex, fc, p_ref, k_ref, cfg, topology):
    """Outputs at the reference and their derivative in each actuator (battery kW, then the three kept shares)."""
    base = ex.solve(fc, p_ref, k_ref, topology)
    y0 = _outputs(base)
    jac = {k: np.zeros(v.shape + (1 + N_GROUPS,)) for k, v in y0.items()}
    lo_kw, hi_kw = -ex.kw_max, ex.kw_max
    up_p, dn_p = np.minimum(p_ref + cfg.probe_kw, hi_kw), np.maximum(p_ref - cfg.probe_kw, lo_kw)
    yu, yd = _outputs(ex.solve(fc, up_p, k_ref, topology)), _outputs(ex.solve(fc, dn_p, k_ref, topology))
    for k in y0:
        jac[k][..., 0] = (yu[k] - yd[k]) / (up_p - dn_p)[None, :, None]
    for g in range(N_GROUPS):
        ku, kd = k_ref.copy(), k_ref.copy()
        ku[:, g] = np.minimum(k_ref[:, g] + cfg.probe_keep, 1.0)
        kd[:, g] = np.maximum(k_ref[:, g] - cfg.probe_keep, 0.0)
        yu, yd = _outputs(ex.solve(fc, p_ref, ku, topology)), _outputs(ex.solve(fc, p_ref, kd, topology))
        for k in y0:
            jac[k][..., 1 + g] = (yu[k] - yd[k]) / (ku[:, g] - kd[:, g])[None, :, None]
    for k in jac:                                        # a failed solve gives no usable derivative
        jac[k] = np.nan_to_num(jac[k], nan=0.0, posinf=0.0, neginf=0.0)
    return base, y0, jac


def _solve_milp(fc, y0, jac, p_ref, k_ref, trust_kw, trust_keep, state, bat, rule, cfg, avail_kw):
    """One MILP round. Columns: c(H) d(H) z(H) keep(3H) e(H) reserve(1) slack(3SH)."""
    s, h = fc.shape
    n_slack = 3 * s * h
    ic, id_, iz, ik, ie, ir, isl = 0, h, 2 * h, 3 * h, 6 * h, 7 * h, 7 * h + 1
    n = isl + n_slack
    cost = np.zeros(n)
    # least curtailment: maximise kept solar weighted by the mean available kW of each group (constant dropped)
    cost[ik:ik + 3 * h] = -cfg.w_curtail * STEP_H * avail_kw.reshape(-1)
    cost[ic:ic + h] = cfg.w_throughput * STEP_H
    cost[id_:id_ + h] = cfg.w_throughput * STEP_H
    cost[ir] = cfg.w_reserve
    cost[isl:] = cfg.w_slack
    lb, ub = np.zeros(n), np.full(n, np.inf)
    ub[ic:ic + h] = bat.kw
    ub[id_:id_ + h] = bat.kw
    ub[iz:iz + h] = 1
    if cfg.curtail:
        lb[ik:ik + 3 * h] = np.maximum(k_ref.reshape(-1) - trust_keep, 0.0)
        ub[ik:ik + 3 * h] = np.minimum(k_ref.reshape(-1) + trust_keep, 1.0)
    else:
        lb[ik:ik + 3 * h] = ub[ik:ik + 3 * h] = 1.0
    lb[ie:ie + h], ub[ie:ie + h] = bat.e_min, bat.e_max
    integrality = np.zeros(n)
    integrality[iz:iz + h] = 1

    rows, cols, vals, rlo, rhi = [], [], [], [], []
    r = 0

    def add(entries, lo, hi):
        nonlocal r
        for c_, v_ in entries:
            rows.append(r)
            cols.append(c_)
            vals.append(v_)
        rlo.append(lo)
        rhi.append(hi)
        r += 1

    eff = bat.efficiency
    for k in range(h):                                   # energy recursion: e[k] after step k
        prev = [] if k == 0 else [(ie + k - 1, -1.0)]
        rhs = state.energy_kwh if k == 0 else 0.0
        add([(ie + k, 1.0), (ic + k, -STEP_H * eff), (id_ + k, STEP_H / eff)] + prev, rhs, rhs)
        add([(ic + k, 1.0), (iz + k, -bat.kw)], -np.inf, 0.0)               # charge only when z = 1
        add([(id_ + k, 1.0), (iz + k, bat.kw)], -np.inf, bat.kw)           # discharge only when z = 0
        add([(ic + k, 1.0), (id_ + k, -1.0)], p_ref[k] - trust_kw, p_ref[k] + trust_kw)     # trust region
    add([(ir, 1.0), (ie + h - 1, 1.0)], bat.kwh * cfg.reserve_soc, np.inf)              # reserve shortfall

    vmax, vmin = rule.vmax_v - cfg.margin_v, rule.vmin_v + cfg.margin_v
    lmax = 100.0 - cfg.margin_loading
    reach_p, reach_k = trust_kw, (trust_keep if cfg.curtail else 0.0)
    for si in range(s):
        for k in range(h):
            act = [(ic + k, 1.0, 0), (id_ + k, -1.0, 0)] + [(ik + 3 * k + g, 1.0, 1 + g) for g in range(N_GROUPS)]
            base_shift = lambda jrow: jrow[0] * p_ref[k] + sum(jrow[1 + g] * k_ref[k, g] for g in range(N_GROUPS))  # noqa: E731
            for kind, (limit_hi, limit_lo, slot) in {"v": (vmax, vmin, 0), "line": (lmax, None, 1),
                                                      "trafo": (lmax, None, 2)}.items():
                y, jj = y0[kind][si, k], jac[kind][si, k]
                ok = np.isfinite(y)
                reach = np.abs(jj[:, 0]) * reach_p + np.abs(jj[:, 1:]).sum(axis=1) * reach_k
                sl = isl + (si * h + k) * 3 + slot
                for m in np.flatnonzero(ok & (y + reach > limit_hi)):
                    add([(c_, jj[m, j] * sign) for c_, sign, j in act] + [(sl, -1.0)], -np.inf,
                        limit_hi - y[m] + base_shift(jj[m]))
                if limit_lo is not None:
                    sl_lo = isl + (si * h + k) * 3 + 1 if kind == "v" else sl          # under-voltage uses slot 1
                    for m in np.flatnonzero(ok & (y - reach < limit_lo)):
                        add([(c_, jj[m, j] * sign) for c_, sign, j in act] + [(sl_lo, 1.0)],
                            limit_lo - y[m] + base_shift(jj[m]), np.inf)
    a = sparse.csr_matrix((vals, (rows, cols)), shape=(r, n))
    res = milp(cost, constraints=LinearConstraint(a, rlo, rhi), integrality=integrality, bounds=Bounds(lb, ub),
               options={"time_limit": cfg.time_limit_s, "disp": False})
    if res.x is None:
        return None
    x = res.x
    slack = x[isl:].reshape(s, h, 3)
    return {"c": x[ic:ic + h], "d": x[id_:id_ + h], "keep": x[ik:ik + 3 * h].reshape(h, 3),
            "e": np.r_[state.energy_kwh, x[ie:ie + h]], "slack": slack, "objective": float(res.fun), "rows": r}


def plan(ex: Executor, fc: StepInputs, state: ControlState, bat: BatteryModel, rule: VoltageRule,
         cfg: PlannerConfig = PlannerConfig(), *, warm: tuple[np.ndarray, np.ndarray] | None = None) -> PlanResult:
    """Plan the horizon `fc` (S retained scenarios x H steps) from the actual `state` on its topology."""
    t0 = time.perf_counter()
    s, h = fc.shape
    topology = state.topology_id
    p_ref = np.zeros(h) if warm is None else warm[0].copy()
    k_ref = np.ones((h, N_GROUPS)) if warm is None else warm[1].copy()
    if not cfg.curtail:
        k_ref[:] = 1.0
    avail = fc.pv_per_kwp[:, :, None] * ex.base.house_kwp[None, None, :]
    groups = ex.group_of_home()
    avail_kw = np.stack([avail[:, :, groups == g].sum(axis=2).mean(axis=0) for g in range(N_GROUPS)], axis=1)   # (H, 3)
    trust_kw, trust_keep = cfg.trust_kw, cfg.trust_keep
    best, rounds = None, []
    for rnd in range(cfg.rounds):
        _, y0, jac = _linearise(ex, fc, p_ref, k_ref, cfg, topology)
        sol = _solve_milp(fc, y0, jac, p_ref, k_ref, trust_kw, trust_keep, state, bat, rule, cfg, avail_kw)
        if sol is None:
            rounds.append({"round": rnd, "milp": "infeasible"})
            break
        p = sol["c"] - sol["d"]
        p = np.clip(p, -bat.kw, bat.kw)
        keep = np.clip(sol["keep"], 0.0, 1.0)
        res = ex.solve(fc, p, keep, topology)
        chk = physical_check(res, rule, vuf_limit=cfg.vuf_limit)
        # how far the linear model was from the real solver at the planned point (voltages, worst over everything)
        pred_v = y0["v"] + jac["v"][..., 0] * (p - p_ref)[None, :, None] + sum(
            jac["v"][..., 1 + g] * (keep[:, g] - k_ref[:, g])[None, :, None] for g in range(N_GROUPS))
        real_v = _outputs(res)["v"]
        miss = float(np.nanmax(np.abs(pred_v - real_v))) if np.isfinite(real_v).any() else float("inf")
        worst = float(np.max(chk.severity))
        infeasible = sorted({int(k) for k in np.argwhere(sol["slack"] > 1e-6)[:, 1]})
        rounds.append({"round": rnd, "trust_kw": round(trust_kw, 2), "trust_keep": round(trust_keep, 3),
                       "rows": sol["rows"], "objective": round(sol["objective"], 4), "prediction_miss_v": round(miss, 3),
                       "worst_severity": round(worst, 3) if np.isfinite(worst) else None,
                       "predicted_infeasible_steps": infeasible, "safe": bool(chk.safe.all())})
        cand = (p, keep, sol, chk, infeasible)
        key = (not chk.safe.all(), worst, sol["objective"])
        if best is None or key < best[0]:
            best = (key, cand)
        if chk.safe.all():
            # standard trust-region rule: the linear model was accurate, so a wider step may cut curtailment further;
            # the best verified plan is kept whatever the next round finds
            at_max = trust_kw >= bat.kw and (trust_keep >= 1.0 or not cfg.curtail)
            if miss <= cfg.margin_v / 2 and not at_max:
                trust_kw, trust_keep = min(trust_kw * 2, bat.kw), min(trust_keep * 2, 1.0)
                p_ref, k_ref = p, keep
                continue
            break
        if miss > cfg.margin_v:                          # the linear model missed: smaller steps around the new point
            trust_kw, trust_keep = max(trust_kw / 2, 1.0), max(trust_keep / 2, 0.05)
        p_ref, k_ref = p, keep
    secs = time.perf_counter() - t0
    if best is None:
        zero = np.zeros(h)
        idle = ex.solve(fc, zero, np.ones((h, N_GROUPS)), topology)
        return PlanResult(zero, zero, zero, np.ones((h, N_GROUPS)), np.full(h + 1, state.energy_kwh), False,
                          physical_check(idle, rule, vuf_limit=cfg.vuf_limit), "optimiser_infeasible", [], 0.0, rounds, secs)
    _, (p, keep, sol, chk, infeasible) = best
    curtailed = float(((1 - keep) * avail_kw).sum() * STEP_H)
    energy = [state.energy_kwh]
    for x in p:
        energy.append(bat.next_energy(energy[-1], float(x)))
    verified = bool(chk.safe.all())
    return PlanResult(p, np.maximum(p, 0), np.maximum(-p, 0), keep, np.array(energy), verified, chk,
                      "verified_safe" if verified else "horizon_unsafe", infeasible, curtailed, rounds, secs)
