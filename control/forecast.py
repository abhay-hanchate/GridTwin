"""Forecasts, simulated observations and the causal forecast correction of the replay.

The forecast issued the evening before is the three retained scenarios of the day's scenario fan
(backend.v2.compute.robust_set: median sun, high grid voltage, high sun). The "observed" day is **simulated**: another
scenario of the same fan that is not retained, plus declared perturbations (a cloud, a demand step, a grid-voltage
shift). It is labelled `simulated_observation`; it is not meter data.

Correction: at the decision boundary the current quarter hour is observed and held for the step. Later steps of the
horizon are corrected by an exponentially weighted residual of what has been observed so far against what was
forecast for those same steps (solar and demand as ratios, grid voltage as a difference), fading with the lead time.
Solar is never corrected where the forecast is dark.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.v2 import compute
from control.execution import StepInputs
from engine.types import DayScenarioBatch, Network

KINDS = ("pv_scale", "load_scale", "upstream_shift")


@dataclass(frozen=True)
class Perturbation:
    kind: str           # pv_scale, load_scale (multiply) or upstream_shift (add, per unit)
    start: int          # first quarter hour (0 = 00:00)
    end: int            # first quarter hour after it
    value: float
    label: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown perturbation {self.kind!r}; one of {KINDS}")


def _inputs(b: DayScenarioBatch, idx) -> StepInputs:
    amb = None if b.ambient_c is None else b.ambient_c[idx]
    return StepInputs(b.load_kw[idx].copy(), b.pv_per_kwp[idx].copy(), b.upstream_pu[idx].copy(), b.t, amb)


def retained_indices(scn: DayScenarioBatch) -> list[int]:
    """The same picks as compute.robust_set: median sun, P90 grid voltage, P90 sun."""
    energy, volts = scn.pv_per_kwp.sum(axis=1), scn.upstream_pu.mean(axis=1)
    pick = lambda values, q: int(np.argmin(np.abs(values - np.quantile(values, q))))  # noqa: E731
    return list(dict.fromkeys([pick(energy, 0.5), pick(volts, 0.9), pick(energy, 0.9)]))


@dataclass
class World:
    all: DayScenarioBatch
    retained: list[int]
    truth_index: int
    forecast: StepInputs            # (3, 96) issued the evening before
    observed: StepInputs            # (1, 96) simulated
    perturbations: tuple[Perturbation, ...]
    provenance: str = "simulated_observation"


def make_world(date: str, net: Network, *, n: int = 100, truth_quantile: float = 0.6,
               perturbations: tuple[Perturbation, ...] = ()) -> World:
    scn = compute.scenarios(date, net, n)
    retained = retained_indices(scn)
    energy = scn.pv_per_kwp.sum(axis=1)
    order = np.argsort(np.abs(energy - np.quantile(energy, truth_quantile)))
    truth = int(next(i for i in order if int(i) not in retained))            # a scenario the forecast did not keep
    obs = _inputs(scn, [truth])
    for p in perturbations:
        sl = slice(p.start, p.end)
        if p.kind == "pv_scale":
            obs.pv_per_kwp[:, sl] *= p.value
        elif p.kind == "load_scale":
            obs.load_kw[:, sl] *= p.value
        else:
            obs.upstream_pu[:, sl] += p.value
    return World(scn, retained, truth, _inputs(scn, retained), obs, tuple(perturbations))


class Corrector:
    """Causal correction of the issued forecast; it only ever sees observations passed to `observe`."""

    def __init__(self, forecast: StepInputs, *, rho: float = 0.3, decay: float = 0.95):
        self.fc, self.rho, self.decay = forecast, rho, decay
        self.b_pv = self.b_load = self.b_up = 0.0
        self.last: dict = {}

    def observe(self, k: int, obs: StepInputs) -> dict:
        """Update the residuals with the observation of step k (shape (1, 1)) against the forecast issued for k."""
        fc_pv = float(self.fc.pv_per_kwp[:, k].mean())
        fc_load = float(self.fc.load_kw[:, k].sum(axis=1).mean())
        fc_up = float(self.fc.upstream_pu[:, k].mean())
        o_pv, o_load, o_up = float(obs.pv_per_kwp[0, 0]), float(obs.load_kw[0, 0].sum()), float(obs.upstream_pu[0, 0])
        r = self.rho
        if fc_pv > 0.02:                                  # solar residual only in daylight
            self.b_pv = r * self.b_pv + (1 - r) * float(np.clip(o_pv / fc_pv - 1, -0.95, 2.0))
        if fc_load > 0:
            self.b_load = r * self.b_load + (1 - r) * float(np.clip(o_load / fc_load - 1, -0.9, 2.0))
        self.b_up = r * self.b_up + (1 - r) * (o_up - fc_up)
        self.last = {"step": k, "forecast": {"pv_per_kwp": fc_pv, "load_kw": fc_load, "upstream_pu": fc_up},
                     "observed": {"pv_per_kwp": o_pv, "load_kw": o_load, "upstream_pu": o_up},
                     "residual": {"pv": round(self.b_pv, 4), "load": round(self.b_load, 4), "upstream_pu": round(self.b_up, 5)}}
        return self.last

    def horizon(self, k: int, h: int, obs_now: StepInputs) -> StepInputs:
        """Forecast for steps k .. k+h-1: step k is the observation now (held for the quarter hour), later steps are
        the issued forecast corrected by the residuals, fading with lead time."""
        steps = list(range(k, min(k + h, self.fc.shape[1])))
        out = self.fc.take(steps)
        s = out.shape[0]
        out.pv_per_kwp[:, 0] = obs_now.pv_per_kwp[0, 0]
        out.load_kw[:, 0] = obs_now.load_kw[0, 0]
        out.upstream_pu[:, 0] = obs_now.upstream_pu[0, 0]
        if out.ambient_c is not None and obs_now.ambient_c is not None:
            out.ambient_c[:, 0] = obs_now.ambient_c[0, 0]
        lead = self.decay ** np.arange(1, len(steps))                            # (h-1,)
        dark = out.pv_per_kwp[:, 1:] <= 0
        out.pv_per_kwp[:, 1:] = np.where(dark, 0.0, np.maximum(out.pv_per_kwp[:, 1:] * (1 + lead * self.b_pv), 0.0))
        out.load_kw[:, 1:] *= (1 + lead * self.b_load)[None, :, None]
        out.upstream_pu[:, 1:] += np.broadcast_to(lead * self.b_up, (s, len(steps) - 1))
        return out
