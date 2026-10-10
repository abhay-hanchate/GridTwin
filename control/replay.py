"""The closed-loop replay: plan 16 quarter hours, execute the first, observe, correct the forecast, plan again.

At every quarter hour of the replay window:
1. Observe the current step (simulated observation) and update the forecast correction with it.
2. Build the horizon: the observation now, then the corrected issued forecast for the three retained scenarios.
3. Plan the horizon from the battery's actual energy (control.planner). When switching is permitted, the budget and
   dwell allow it, and the plan on the current topology is unsafe or curtails, plan once more for each permitted
   topology and keep the best verified plan.
4. Check the plan's first action against the storage and switching rules, then solve it at the observed step in the
   real solver. Verified safe: execute. Otherwise: control.fallback.
5. Commit the executed action: energy, topology and operation count change only now. Record the transition.

The comparison runs the existing reactive battery rule (engine.fixes.battery) on the identical observations, battery,
node and starting energy. Nothing here changes engine/.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from backend.v2 import compute
from control import fallback
from control.execution import BASE, Executor, StepInputs
from control.forecast import Corrector, Perturbation, make_world
from control.planner import PlannerConfig, PlanResult, plan
from control.types import (STEP_H, Action, BatteryModel, ControlState, Status, StepRecord, SwitchPolicy,
                           operations_for)
from control.verify import action_errors, physical_check
from engine.fixes import switching
from engine.fixes.catalog import worst_node
from engine.fixes.battery import solve_with_battery
from engine.types import BatterySpec, Controls, DayScenarioBatch

TRIGGER_PV, TRIGGER_LOAD, TRIGGER_UP_V, TRIGGER_MARGIN_V = 0.15, 0.15, 2.0, 2.0


@dataclass(frozen=True)
class ReplayConfig:
    run_id: str = "custom"
    title: str = ""
    network_id: str = "benchmark_250"
    date: str = "2025-05-15"
    rule_id: str = "pm10"
    start: int = 36                      # first quarter hour (36 = 09:00)
    end: int = 72                        # first quarter hour after the window
    horizon: int = 16
    battery_kw: float = 30.0
    battery_kwh: float = 60.0
    soc_start: float = 0.5
    soc_min: float = 0.10
    soc_max: float = 0.90
    efficiency: float = 0.95
    battery_node: int | None = None      # None: the street's highest-voltage node
    curtail: bool = True
    switching: bool = False
    n_switches: int = 3
    max_operations: int = 2
    dwell_steps: int = 8
    tap_pos: int = 0                     # off-load tap changer: fixed for the whole run
    vuf_limit: float | None = None
    n_scenarios: int = 100
    truth_quantile: float = 0.6
    perturbations: tuple[Perturbation, ...] = ()
    rho: float = 0.3
    decay: float = 0.95

    def battery(self) -> BatteryModel:
        return BatteryModel(self.battery_kw, self.battery_kwh, self.efficiency, self.soc_min, self.soc_max)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["perturbations"] = [asdict(p) for p in self.perturbations]
        return d


@dataclass
class Replay:
    config: dict
    provenance: dict
    switches: list[dict]
    records: list[StepRecord]
    baseline: dict
    summary: dict
    timing: dict
    issued_forecast: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = asdict(self)
        out["records"] = [asdict(r) for r in self.records]
        return out


def _r(x, n=3):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def _check_dict(chk, i=0, j=0) -> dict:
    return {"safe": bool(chk.safe[i, j]), "v_max_v": _r(chk.v_max_v[i, j], 2), "v_min_v": _r(chk.v_min_v[i, j], 2),
            "line_max_pct": _r(chk.line_max_pct[i, j], 1), "trafo_pct": _r(chk.trafo_pct[i, j], 1),
            "vuf_pct": _r(chk.vuf_pct[i, j], 2), "margin_v": _r(chk.margin_v[i, j], 2),
            "severity": _r(chk.severity[i, j], 3), "reasons": chk.reasons[i][j]}


def _switch_options(net, n: int) -> tuple[list[dict], dict]:
    """The permitted topologies: hypothetical ties from feeder-end geometry, never installed equipment."""
    descs, nets = [], {}
    for rec in switching.candidates(net)[:n]:
        a, b = int(net.line_from[rec.opened_line]), int(net.line_to[rec.opened_line])
        tid = f"tie_{rec.tie[0]}_{rec.tie[1]}_open_{a}_{b}"
        descs.append({"id": tid, "close": list(rec.tie), "open": [a, b], "tie_length_m": round(rec.tie_length_m, 1),
                      "status": "hypothetical (inferred from feeder-end geometry, not an installed switch)"})
        nets[tid] = switching.apply(net, rec)
    return descs, nets


def _baseline(cfg: ReplayConfig, net, node: int, world, rule, ex: Executor) -> dict:
    """The existing reactive battery rule on the identical observed window, unity power factor like the controller."""
    w = list(range(cfg.start, cfg.end))
    obs = world.observed.take(w)
    batch = DayScenarioBatch(obs.t, obs.load_kw, obs.pv_per_kwp, obs.upstream_pu, ex.load_pf(), ("observed",),
                             obs.ambient_c)
    spec = BatterySpec(kw=cfg.battery_kw, kwh=cfg.battery_kwh, node=node, efficiency=cfg.efficiency,
                       soc_min=cfg.soc_min, soc_max=cfg.soc_max, soc_start=cfg.soc_start)
    t0 = time.perf_counter()
    res = solve_with_battery(net, batch, spec, rule, Controls(tap_pos=cfg.tap_pos))
    secs = time.perf_counter() - t0
    chk = physical_check(res, rule, vuf_limit=cfg.vuf_limit)
    bat = cfg.battery()
    energy = [cfg.soc_start * cfg.battery_kwh]
    for p in res.battery_kw[0]:
        energy.append(bat.next_energy(energy[-1], float(p)))
    return {"name": "reactive battery rule (engine.fixes.battery), same observations",
            "battery_kw": [_r(x, 3) for x in res.battery_kw[0]], "energy_kwh": [_r(x, 4) for x in energy],
            "safe": [bool(x) for x in chk.safe[0]], "v_max_v": [_r(x, 2) for x in chk.v_max_v[0]],
            "v_min_v": [_r(x, 2) for x in chk.v_min_v[0]], "severity": [_r(x, 3) for x in chk.severity[0]],
            "unsafe_steps": int((~chk.safe[0]).sum()), "curtailed_kwh": 0.0,
            "throughput_kwh": _r(float(np.abs(res.battery_kw[0]).sum() * STEP_H), 3), "seconds": _r(secs, 3)}


def run(cfg: ReplayConfig) -> Replay:
    t_start = time.perf_counter()
    net, rule = compute.network(cfg.network_id), compute.rule(cfg.rule_id)
    world = make_world(cfg.date, net, n=cfg.n_scenarios, truth_quantile=cfg.truth_quantile,
                       perturbations=cfg.perturbations)
    retained = DayScenarioBatch(world.all.t, world.all.load_kw[world.retained], world.all.pv_per_kwp[world.retained],
                                world.all.upstream_pu[world.retained], world.all.load_pf)
    node = cfg.battery_node if cfg.battery_node is not None else worst_node(net, retained)
    ex = Executor(net, battery_node=node, battery_kw_max=cfg.battery_kw, tap_pos=cfg.tap_pos)
    descs, nets = _switch_options(net, cfg.n_switches) if cfg.switching else ([], {})
    for tid, n in nets.items():
        ex.add_topology(tid, n)
    policy = SwitchPolicy(tuple(nets), cfg.max_operations, cfg.dwell_steps)
    bat = cfg.battery()
    pcfg = PlannerConfig(curtail=cfg.curtail, vuf_limit=cfg.vuf_limit)
    corr = Corrector(world.forecast, rho=cfg.rho, decay=cfg.decay)
    state = ControlState(energy_kwh=cfg.soc_start * cfg.battery_kwh)
    warm: tuple[np.ndarray, np.ndarray] | None = None
    records, latencies, plan_secs = [], [], []
    for k in range(cfg.start, cfg.end):
        t_step = time.perf_counter()
        obs_now = world.observed.take([k])
        fc_info = corr.observe(k, obs_now)
        h = min(cfg.horizon, world.forecast.shape[1] - k)
        fc_h = corr.horizon(k, h, obs_now)
        triggers = ["every quarter hour"]
        res_ = fc_info["residual"]
        if abs(res_["pv"]) > TRIGGER_PV:
            triggers.append(f"solar residual {res_['pv']:+.0%}")
        if abs(res_["load"]) > TRIGGER_LOAD:
            triggers.append(f"demand residual {res_['load']:+.0%}")
        if abs(res_["upstream_pu"]) * 230 > TRIGGER_UP_V:
            triggers.append(f"grid voltage residual {res_['upstream_pu'] * 230:+.1f} V")

        # 3. plan on the current topology; consider permitted switching when it would help
        best: tuple[PlanResult, str] = (plan(ex, fc_h, state, bat, rule, pcfg, warm=warm), state.topology_id)
        options = [BASE] + list(nets) if state.topology_id != BASE else list(nets)
        if cfg.switching and (not best[0].verified or best[0].curtailed_kwh > 0.5):
            for tid in options:
                if tid == state.topology_id or action_errors(state, Action(topology_id=tid), bat, policy, k):
                    continue
                alt = plan(ex, fc_h, replace(state, topology_id=tid), bat, rule, pcfg)
                if (not alt.verified, alt.curtailed_kwh + 0.5 * operations_for(state.topology_id, tid)) < \
                        (not best[0].verified, best[0].curtailed_kwh):
                    best = (alt, tid)
        planned, topo = best
        plan_secs.append(planned.seconds)
        if topo != state.topology_id and topo != BASE:
            triggers.append(f"switching considered: {topo}")
        if planned.check.margin_v.size and np.nanmin(planned.check.margin_v[:, :2]) < TRIGGER_MARGIN_V:
            triggers.append("near a voltage limit in the next half hour")

        # 4. first action: rules, then the real solver at the observed step
        first = Action(float(planned.battery_kw[0]), tuple(float(x) for x in planned.keep[0]), topo, "plan")
        errs = action_errors(state, first, bat, policy, k)
        topo_before = state.topology_id
        if errs:
            chk_first, status, reason = None, Status.INVALID_ACTION, "; ".join(errs)
        else:
            r1 = ex.solve(obs_now, np.array([first.battery_kw]), np.array([first.keep]), first.topology_id)
            chk_first = physical_check(r1, rule, vuf_limit=cfg.vuf_limit)
            status, reason = ((Status.VERIFIED_SAFE, "planned action verified at the observed step")
                              if chk_first.safe[0, 0] else (None, "; ".join(chk_first.reasons[0][0]) or "unsafe"))
        if status is Status.VERIFIED_SAFE:
            action, after = first, chk_first
        else:
            why = "planned action invalid: " + reason if status is Status.INVALID_ACTION else \
                "planned action unsafe at the observed step: " + reason
            fb = fallback.search(ex, obs_now, state, bat, rule, curtail=cfg.curtail, vuf_limit=cfg.vuf_limit)
            action, after, status = fb.action, fb.check, fb.status
            reason = f"{why}; {fb.reason}"
            if planned.status == "optimiser_infeasible":
                reason = "optimiser infeasible (not proof of physical impossibility); " + reason
        before_res = ex.solve(obs_now, np.zeros(1), np.ones((1, 3)), topo_before)
        before = physical_check(before_res, rule, vuf_limit=cfg.vuf_limit)

        # 5. commit
        e0 = state.energy_kwh
        e1 = bat.next_energy(e0, action.battery_kw)
        ops = operations_for(state.topology_id, action.topology_id)
        state = ControlState(e1, action.topology_id, state.operations_used + ops,
                             k if ops else state.last_switch_step)
        avail = obs_now.pv_per_kwp[0, 0] * net.house_kwp
        groups = ex.group_of_home()
        curtailed = float(sum((1 - action.keep[g]) * avail[groups == g].sum() for g in range(3)) * STEP_H)
        records.append(StepRecord(
            step=k, time=str(world.all.t[k].strftime("%H:%M")), energy_before_kwh=_r(e0, 4), energy_after_kwh=_r(e1, 4),
            soc_before=_r(e0 / bat.kwh, 4), soc_after=_r(e1 / bat.kwh, 4),
            action={"battery_kw": _r(action.battery_kw, 3), "keep": [_r(x, 3) for x in action.keep],
                    "topology_id": action.topology_id, "source": action.source, "curtailed_kwh": _r(curtailed, 4)},
            status=status.value, reason=reason, replan_triggers=triggers, topology_before=topo_before,
            topology_after=state.topology_id, operations_used=state.operations_used,
            operations_left=policy.max_operations - state.operations_used,
            planner={**planned.summary(), "horizon": planned.horizon},
            before=_check_dict(before), after=_check_dict(after),
            forecast={k_: v for k_, v in fc_info.items() if k_ != "step"},
            plan_horizon=[{"battery_kw": _r(p, 3), "keep": [_r(x, 3) for x in kk], "energy_kwh": _r(e, 3)}
                          for p, kk, e in zip(planned.battery_kw, planned.keep, planned.energy_kwh[1:])]))
        warm = (np.r_[planned.battery_kw[1:], 0.0], np.r_[planned.keep[1:], np.ones((1, 3))])
        latencies.append(time.perf_counter() - t_step)

    base = _baseline(cfg, net, node, world, rule, ex)
    ours_unsafe = sum(r.status != Status.VERIFIED_SAFE.value for r in records)
    statuses = {s.value: sum(r.status == s.value for r in records) for s in Status}
    energy = [records[0].energy_before_kwh] + [r.energy_after_kwh for r in records]
    infeasible = [{"step": r.step, "time": r.time, "status": r.status, "reason": r.reason}
                  for r in records if r.status != Status.VERIFIED_SAFE.value]
    summary = {
        "steps": len(records), "horizon": cfg.horizon, "statuses": statuses,
        "unsafe_steps": ours_unsafe, "baseline_unsafe_steps": base["unsafe_steps"],
        "unsafe_steps_without_control": sum(not r.before["safe"] for r in records),
        "curtailed_kwh": _r(sum(r.action["curtailed_kwh"] for r in records), 3),
        "throughput_kwh": _r(sum(abs(r.action["battery_kw"]) for r in records) * STEP_H, 3),
        "baseline_throughput_kwh": base["throughput_kwh"],
        "soc_min": _r(min(energy) / bat.kwh, 4), "soc_max": _r(max(energy) / bat.kwh, 4),
        "soc_final": _r(energy[-1] / bat.kwh, 4), "operations_used": records[-1].operations_used,
        "fallbacks": sum(r.action["source"] != "plan" for r in records),
        "replans": len(records), "infeasible_periods": _periods(infeasible),
        "worst_after_severity": _r(max((r.after["severity"] or 0) if r.after["severity"] is not None else float("inf")
                                       for r in records), 3),
    }
    lat = np.array(latencies)
    timing = {"total_s": _r(time.perf_counter() - t_start, 2), "step_p50_s": _r(np.percentile(lat, 50), 3),
              "step_p95_s": _r(np.percentile(lat, 95), 3), "plan_p50_s": _r(np.percentile(plan_secs, 50), 3),
              "baseline_s": base["seconds"]}
    provenance = {"observations": f"{world.provenance}: scenario {world.truth_index} of the day's fan "
                  "(not one of the three retained forecast scenarios) with the declared perturbations; not meter data",
                  "forecast": f"issued: retained scenarios {world.retained} of {cfg.n_scenarios} for {cfg.date}",
                  "street": "benchmark street (SimBench topology, IS 398 conductors), not a surveyed feeder",
                  "battery_node": node, "tap": f"{cfg.tap_pos}, fixed for the run (off-load tap changer)",
                  "voltage_rule": rule.id, "unbalance_limit": cfg.vuf_limit}
    issued = {"pv_per_kwp": [_r(x, 4) for x in world.forecast.pv_per_kwp.mean(0)],
              "observed_pv_per_kwp": [_r(x, 4) for x in world.observed.pv_per_kwp[0]],
              "load_kw": [_r(x, 3) for x in world.forecast.load_kw.sum(2).mean(0)],
              "observed_load_kw": [_r(x, 3) for x in world.observed.load_kw[0].sum(1)],
              "upstream_v": [_r(x * 230, 2) for x in world.forecast.upstream_pu.mean(0)],
              "observed_upstream_v": [_r(x * 230, 2) for x in world.observed.upstream_pu[0]],
              "t": [x.strftime("%H:%M") for x in world.all.t]}
    return Replay(cfg.to_dict(), provenance, descs, records, base, summary, timing, issued)


def _periods(rows: list[dict]) -> list[dict]:
    """Consecutive non-safe steps grouped into periods."""
    out: list[dict] = []
    for r in rows:
        if out and out[-1]["last_step"] == r["step"] - 1:
            out[-1].update(last_step=r["step"], until=r["time"], steps=out[-1]["steps"] + 1)
            out[-1]["statuses"] = sorted(set(out[-1]["statuses"]) | {r["status"]})
        else:
            out.append({"first_step": r["step"], "last_step": r["step"], "from": r["time"], "until": r["time"],
                        "steps": 1, "statuses": [r["status"]], "first_reason": r["reason"]})
    return out
