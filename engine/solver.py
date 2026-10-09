"""Day solver: Network + scenarios + controls -> DayResult, on the power-grid-model batch engine.

All scenarios and all 96 steps are one batch dimension (B = S x T). Smart-inverter control is a damped
fixed point over whole batches (about 8-10 passes), not a Python loop over steps.
"""
from __future__ import annotations

import numpy as np
from power_grid_model import CalculationMethod, LoadGenType, PowerGridModel, WindingType, initialize_array
from power_grid_model.enum import BranchSide
from power_grid_model.errors import PowerGridBatchError

from engine.types import Controls, DayResult, DayScenarioBatch, Network

NOMINAL_V = 230.0
SOURCE_ID, TRAFO_ID, LINE0, LOAD0, GEN0 = 5000, 2000, 10_000, 100_000, 200_000
_WINDING = {"delta": WindingType.delta, "wye": WindingType.wye, "wye_n": WindingType.wye_n}
A_OP = np.exp(2j * np.pi / 3)


class PgmBackend:
    """Thin adapter over PowerGridModel for one Network; one generator slot per home (zero where no PV)."""

    def __init__(self, net: Network, asymmetric: bool = True):
        self.net, self.asym = net, asymmetric
        n, n_l, n_h = net.n_nodes, net.n_lines, net.n_homes
        node = initialize_array("input", "node", n)
        node["id"] = np.arange(n)
        node["u_rated"] = net.node_kv * 1000

        line = initialize_array("input", "line", n_l)
        line["id"] = LINE0 + np.arange(n_l)
        line["from_node"], line["to_node"] = net.line_from, net.line_to
        line["from_status"] = line["to_status"] = 1
        line["r1"], line["x1"], line["c1"], line["tan1"] = net.line_r1_ohm, net.line_x1_ohm, net.line_c1_f, 0.0
        line["r0"], line["x0"], line["c0"], line["tan0"] = net.line_r0_ohm, net.line_x0_ohm, net.line_c1_f, 0.0
        line["i_n"] = net.line_i_n_a

        tr_spec = net.trafo
        tr = initialize_array("input", "transformer", 1)
        tr["id"], tr["from_node"], tr["to_node"] = TRAFO_ID, tr_spec.from_node, tr_spec.to_node
        tr["from_status"] = tr["to_status"] = 1
        tr["u1"], tr["u2"], tr["sn"] = tr_spec.u1_v, tr_spec.u2_v, tr_spec.sn_va
        tr["uk"], tr["pk"], tr["i0"], tr["p0"] = tr_spec.uk, tr_spec.pk_w, tr_spec.i0, tr_spec.p0_w
        tr["winding_from"], tr["winding_to"] = _WINDING[tr_spec.winding_from], _WINDING[tr_spec.winding_to]
        tr["clock"] = tr_spec.clock
        tr["tap_side"] = BranchSide.from_side
        tr["tap_pos"], tr["tap_min"], tr["tap_max"] = 0, tr_spec.tap_min, tr_spec.tap_max
        tr["tap_nom"], tr["tap_size"] = tr_spec.tap_nom, tr_spec.tap_size_v

        src = initialize_array("input", "source", 1)
        src["id"], src["node"], src["status"], src["u_ref"] = SOURCE_ID, net.source_node, 1, 1.0

        kind = "asym" if asymmetric else "sym"
        self.kind = kind
        load = initialize_array("input", f"{kind}_load", n_h)
        load["id"], load["node"], load["status"], load["type"] = LOAD0 + np.arange(n_h), net.house_node, 1, LoadGenType.const_power
        gen = initialize_array("input", f"{kind}_gen", n_h)
        gen["id"], gen["node"], gen["status"], gen["type"] = GEN0 + np.arange(n_h), net.house_node, 1, LoadGenType.const_power
        self.load_id, self.gen_id = load["id"].copy(), gen["id"].copy()

        data = {"node": node, "line": line, "transformer": tr, "source": src,
                f"{kind}_load": load, f"{kind}_gen": gen}
        self._data = data
        self.model = PowerGridModel(data, system_frequency=50.0)
        self._models: dict[float, PowerGridModel] = {}
        self.onehot = np.eye(3)[net.house_phase]                       # (H, 3)
        self.lv = net.lv_nodes

    def _spread(self, a: np.ndarray) -> np.ndarray:
        """(B, H) per-home watts -> (B, H, 3) with each home on its own phase (asymmetric) or unchanged."""
        return a[:, :, None] * self.onehot[None, :, :] if self.asym else a

    def _model_for(self, scale: float) -> PowerGridModel:
        """Line resistance cannot change inside a batch update, so each resistance bin gets its own cached model."""
        if scale not in self._models:
            lines = self._data["line"].copy()
            lines["r1"], lines["r0"] = lines["r1"] * scale, lines["r0"] * scale
            self._models[scale] = PowerGridModel({**self._data, "line": lines}, system_frequency=50.0)
        return self._models[scale]

    def calculate(self, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos: int, r_scale=None, step: float = 0.02) -> dict:
        if r_scale is None:
            return self._calculate_with(self.model, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos)
        bins = np.round(np.asarray(r_scale) / step) * step
        out = None
        for value in np.unique(bins):
            idx = np.flatnonzero(bins == value)
            part = self._calculate_with(self._model_for(float(round(value, 6))), p_load_w[idx], q_load_w[idx], p_gen_w[idx],
                                        q_gen_w[idx], upstream_pu[idx], tap_pos)
            if out is None:
                out = {k: np.empty((len(upstream_pu),) + v.shape[1:], dtype=v.dtype) for k, v in part.items()}
            for k, v in part.items():
                out[k][idx] = v
        return out

    def _calculate_with(self, model, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos: int) -> dict:
        b, n_h = p_load_w.shape
        ul = initialize_array("update", f"{self.kind}_load", (b, n_h))
        ul["id"], ul["p_specified"], ul["q_specified"] = self.load_id, self._spread(p_load_w), self._spread(q_load_w)
        ug = initialize_array("update", f"{self.kind}_gen", (b, n_h))
        ug["id"], ug["p_specified"], ug["q_specified"] = self.gen_id, self._spread(p_gen_w), self._spread(q_gen_w)
        us = initialize_array("update", "source", (b, 1))
        us["id"], us["u_ref"] = SOURCE_ID, upstream_pu[:, None]
        ut = initialize_array("update", "transformer", (b, 1))
        ut["id"], ut["tap_pos"] = TRAFO_ID, tap_pos
        update = {f"{self.kind}_load": ul, f"{self.kind}_gen": ug, "source": us, "transformer": ut}

        def run(continue_on_error: bool):
            return model.calculate_power_flow(
                symmetric=not self.asym, error_tolerance=1e-8, max_iterations=40,
                calculation_method=CalculationMethod.newton_raphson, update_data=update,
                continue_on_batch_error=continue_on_error)

        failed = np.array([], dtype=int)
        try:
            res = run(False)
        except PowerGridBatchError as err:           # rare: recover the good rows, mask the bad ones
            failed = np.asarray(err.failed_scenarios, dtype=int)
            res = run(True)
        return self._extract(res, b, failed)

    def _trafo_loading(self, i_from, i_to) -> np.ndarray:
        """Current-based loading in percent (the thermal measure, as in pandapower), worst phase if unbalanced.

        power-grid-model's own `loading` is apparent power over rating, which reads higher whenever the
        voltage is above nominal, so it is not used.
        """
        spec = self.net.trafo
        rated_from = spec.sn_va / (np.sqrt(3) * spec.u1_v)
        rated_to = spec.sn_va / (np.sqrt(3) * spec.u2_v)
        i_from, i_to = np.asarray(i_from, dtype=float), np.asarray(i_to, dtype=float)
        worst_from = i_from if i_from.ndim == 1 else i_from.max(axis=-1)
        worst_to = i_to if i_to.ndim == 1 else i_to.max(axis=-1)
        return np.maximum(worst_from / rated_from, worst_to / rated_to) * 100

    def _extract(self, res: dict, b: int, failed: np.ndarray) -> dict:
        lv = self.lv
        node, line, trf = res["node"], res["line"], res["transformer"]
        if self.asym:
            u = node["u_pu"][:, lv, :].astype(float)
            ang = node["u_angle"][:, lv, :]
            v = u * np.exp(1j * ang)
            v1 = (v[..., 0] + A_OP * v[..., 1] + A_OP ** 2 * v[..., 2]) / 3
            v2 = (v[..., 0] + A_OP ** 2 * v[..., 1] + A_OP * v[..., 2]) / 3
            vuf = (np.abs(v2) / np.maximum(np.abs(v1), 1e-9)).max(axis=1) * 100
            # Phase currents at the transformer's LV side from S = V I*; the neutral carries their sum.
            nt = self.net.trafo.to_node
            v_to = node["u"][:, nt, :] * np.exp(1j * node["u_angle"][:, nt, :])
            s_to = trf["p_to"][:, 0, :] + 1j * trf["q_to"][:, 0, :]
            neutral = np.abs(np.conj(s_to / v_to).sum(axis=1))
            trafo_loading = self._trafo_loading(trf["i_from"][:, 0, :], trf["i_to"][:, 0, :])
            p_line = (line["p_from"] + line["p_to"]).sum(axis=-1).sum(axis=-1)
            q_line = (line["q_from"] + line["q_to"]).sum(axis=-1).sum(axis=-1)
            p_trf_in = trf["p_from"][:, 0, :].sum(axis=-1)
            p_trf_loss = (trf["p_from"] + trf["p_to"])[:, 0, :].sum(axis=-1)
            q_trf_loss = (trf["q_from"] + trf["q_to"])[:, 0, :].sum(axis=-1)
        else:
            u = np.repeat(node["u_pu"][:, lv, None], 3, axis=2).astype(float)
            vuf, neutral = np.zeros(b), np.zeros(b)
            p_line = (line["p_from"] + line["p_to"]).sum(axis=-1)
            q_line = (line["q_from"] + line["q_to"]).sum(axis=-1)
            trafo_loading = self._trafo_loading(trf["i_from"][:, 0], trf["i_to"][:, 0])
            p_trf_in = trf["p_from"][:, 0]
            p_trf_loss = (trf["p_from"] + trf["p_to"])[:, 0]
            q_trf_loss = (trf["q_from"] + trf["q_to"])[:, 0]
        out = {
            "u_pu": u,
            "line_loading_pct": np.asarray(line["loading"], dtype=float) * 100,
            "trafo_loading_pct": trafo_loading,
            "trafo_p_kw": p_trf_in / 1000,
            "losses_kw": (p_line + p_trf_loss) / 1000,
            "q_loss_kvar": (q_line + q_trf_loss) / 1000,
            "neutral_a": neutral, "vuf_pct": vuf,
            "converged": np.ones(b, dtype=bool),
        }
        if len(failed):
            out["converged"][failed] = False
            for key in ("u_pu", "line_loading_pct", "trafo_loading_pct", "trafo_p_kw", "losses_kw",
                        "q_loss_kvar", "neutral_a", "vuf_pct"):
                out[key] = out[key].astype(float)
                out[key][failed] = np.nan
        return out


class DaySolver:
    def __init__(self, network: Network, *, asymmetric: bool = True, backend: str = "pgm"):
        if backend != "pgm":
            raise ValueError("only the power-grid-model backend is available; the pandapower reference lives in engine.reference")
        self.network, self.asymmetric = network, asymmetric
        self.backend = PgmBackend(network, asymmetric)
        self._h_idx = np.array([int(np.flatnonzero(network.lv_nodes == n)[0]) for n in network.house_node])
        self.max_passes, self.damping, self.tol_kw = 80, 0.3, 1e-3

    def solve(self, scn: DayScenarioBatch, controls: Controls = Controls()) -> DayResult:
        if controls.battery is not None:
            raise NotImplementedError("battery control is a sequential solve added in the fix-tournament phase")
        net, (s, t) = self.network, scn.shape
        b, n_h = s * t, net.n_homes
        load_kw = scn.load_kw.reshape(b, n_h)
        p_load = load_kw * 1000.0
        q_load = p_load * np.tan(np.arccos(scn.load_pf))
        up = scn.upstream_pu.reshape(b)
        pv_avail = scn.pv_per_kwp.reshape(b, 1) * net.house_kwp[None, :]                    # kW
        p_cap = pv_avail.copy()
        if controls.curtail_keep is not None:
            p_cap *= controls.curtail_keep
        if controls.export_limit_kw is not None:
            lim = np.broadcast_to(np.asarray(controls.export_limit_kw, float), (t, n_h))
            p_cap = np.minimum(p_cap, load_kw + np.tile(lim, (s, 1)))
        sn_kw = net.house_kwp * controls.inverter_s_factor
        p, q = p_cap.copy(), np.zeros_like(p_cap)
        if controls.pf_fixed is not None:
            q = -p * np.tan(np.arccos(controls.pf_fixed))

        r_scale = None
        if scn.ambient_c is not None:
            t_cond = scn.ambient_c.reshape(b) + net.conductor_delta_t_c
            r_scale = 1 + net.conductor_alpha * (t_cond - 20.0)           # IS 398 resistances are DC at 20 degrees C

        def run(p_kw, q_kw):
            return self.backend.calculate(p_load, q_load, p_kw * 1000, q_kw * 1000, up, controls.tap_pos, r_scale)

        res, passes, unsettled = run(p, q), 1, np.zeros(b, dtype=bool)
        if controls.volt_var is not None or controls.volt_watt is not None:
            for _ in range(self.max_passes):
                v = res["u_pu"][:, self._h_idx, net.house_phase]                             # (B, H)
                v = np.where(np.isfinite(v), v, 1.0)
                p_t = np.minimum(p_cap, sn_kw * controls.volt_watt.p_fraction(v)) if controls.volt_watt else p_cap
                cap = np.sqrt(np.maximum(sn_kw ** 2 - p_t ** 2, 0.0))
                q_t = np.clip(sn_kw * controls.volt_var.q_fraction(v), -cap, cap) if controls.volt_var else np.zeros_like(p)
                dp, dq = p_t - p, q_t - q
                delta = np.maximum(np.abs(dp), np.abs(dq)).max(axis=1)
                unsettled = delta >= self.tol_kw
                if not unsettled.any():
                    break
                p, q = p + self.damping * dp, q + self.damping * dq
                res = run(p, q)
                passes += 1
        converged = res["converged"] & ~unsettled

        def shape(a):
            return a.reshape((s, t) + a.shape[1:])

        return DayResult(
            t=scn.t, u_pu=shape(res["u_pu"]), line_loading_pct=shape(res["line_loading_pct"]),
            trafo_loading_pct=shape(res["trafo_loading_pct"]), trafo_p_kw=shape(res["trafo_p_kw"]),
            losses_kw=shape(res["losses_kw"]), q_loss_kvar=shape(res["q_loss_kvar"]),
            pv_kw=shape(p.sum(axis=1)), pv_avail_kw=shape(pv_avail.sum(axis=1)),
            inverter_kvar=shape(-q.sum(axis=1)), battery_kw=np.zeros((s, t)),
            neutral_a=shape(res["neutral_a"]), vuf_pct=shape(res["vuf_pct"]),
            converged=shape(converged), passes=passes,
        )
