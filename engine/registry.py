"""F4: one registry of every change, fix and check the what-if tool can run.

Each entry has an id, a kind, a label and a Pydantic parameter model; the API lists them (GET /catalog) and runs any
combination (POST /whatif) without new endpoints. Parameter bounds live in the models, so validation and the
dashboard's form come from one place.

  change.*  modify the street or the day      (network, scenarios, params) -> (network, scenarios)
  fix.*     a corrective action               params -> Controls (battery: a BatterySpec, solved sequentially)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import numpy as np
from pydantic import BaseModel, Field

from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str                     # change, fix or check
    label: str
    description: str
    params: type[BaseModel]
    fn: Callable | None = None

    def describe(self) -> dict:
        return {"id": self.id, "kind": self.kind, "label": self.label, "description": self.description,
                "params": self.params.model_json_schema()}


REGISTRY: dict[str, Entry] = {}


def register(id: str, kind: str, label: str, description: str, params: type[BaseModel]):
    def wrap(fn):
        if id in REGISTRY:
            raise ValueError(f"duplicate registry id {id!r}")
        REGISTRY[id] = Entry(id, kind, label, description, params, fn)
        return fn
    return wrap


def catalog() -> list[dict]:
    return [e.describe() for e in REGISTRY.values()]


# ---- changes ---------------------------------------------------------------------------------------------------

class PanelSize(BaseModel):
    kwp_per_home: float = Field(3.0, ge=0, le=10, description="installed solar per home with solar, kW")


@register("change.panel_size", "change", "Bigger or smaller rooftop systems",
          "Every home that has solar gets this size instead of 3 kW.", PanelSize)
def _panel_size(net: Network, scn: DayScenarioBatch, p: PanelSize):
    return net.with_pv(np.where(net.house_kwp > 0, p.kwp_per_home, 0.0)), scn


class UpstreamShift(BaseModel):
    shift_pct: float = Field(0.0, ge=-10, le=10, description="change of the voltage arriving from the grid, % of 230 V")


@register("change.upstream_shift", "change", "Grid voltage higher or lower",
          "Shifts the voltage arriving at the transformer for the whole day.", UpstreamShift)
def _upstream_shift(net: Network, scn: DayScenarioBatch, p: UpstreamShift):
    return net, replace(scn, upstream_pu=scn.upstream_pu + p.shift_pct / 100)


class EvCharging(BaseModel):
    share_of_homes: float = Field(0.2, ge=0, le=1, description="share of homes with an EV charger")
    kw: float = Field(3.3, gt=0, le=11, description="charger power, kW")
    start_hour: int = Field(19, ge=0, le=23)
    hours: int = Field(4, ge=1, le=12)


@register("change.ev_charging", "change", "Evening EV charging",
          "A share of homes (spread along the street) charge an EV every evening.", EvCharging)
def _ev(net: Network, scn: DayScenarioBatch, p: EvCharging):
    n = net.n_homes
    homes = np.zeros(n, dtype=bool)
    homes[np.round(np.linspace(0, n - 1, int(round(p.share_of_homes * n)))).astype(int)] = True
    steps = (np.arange(scn.shape[1]) // 4 - p.start_hour) % 24 < p.hours
    extra = np.where(steps[:, None] & homes[None, :], p.kw, 0.0)
    return net, replace(scn, load_kw=scn.load_kw + extra[None, :, :])


class Heatwave(BaseModel):
    load_factor: float = Field(1.3, ge=1, le=2, description="multiplier on every home's demand (fans and AC)")


@register("change.heatwave", "change", "Heatwave demand", "Scales every home's demand for the whole day.", Heatwave)
def _heat(net: Network, scn: DayScenarioBatch, p: Heatwave):
    return net, replace(scn, load_kw=scn.load_kw * p.load_factor)


# ---- fixes -----------------------------------------------------------------------------------------------------

class Tap(BaseModel):
    tap_pos: int = Field(1, ge=-2, le=2, description="transformer tap steps (+ lowers the street voltage by 2.5% each)")


@register("fix.tap", "fix", "Transformer tap", "Off-load tap change, set once for the season.", Tap)
def _tap(c: Controls, p: Tap) -> Controls:
    return replace(c, tap_pos=p.tap_pos)


class NoParams(BaseModel):
    pass


@register("fix.volt_var", "fix", "Smart inverters: IEEE 1547 Volt/VAR",
          "Category B default curve on every inverter; absorbs reactive power only where voltage is high.", NoParams)
def _vv(c: Controls, p: NoParams) -> Controls:
    return replace(c, volt_var=VoltVarCurve())


@register("fix.volt_watt", "fix", "Smart inverters: IEEE 1547 Volt/Watt",
          "Caps output above 1.06 pu, down to 20% of rating at 1.10 pu.", NoParams)
def _vw(c: Controls, p: NoParams) -> Controls:
    return replace(c, volt_watt=VoltWattCurve())


class Curtail(BaseModel):
    keep: float = Field(0.8, ge=0, le=1, description="share of solar output allowed out")


@register("fix.curtail", "fix", "Uniform export cap", "Every panel may send out only this share of its output.", Curtail)
def _curtail(c: Controls, p: Curtail) -> Controls:
    return replace(c, curtail_keep=p.keep)


class Battery(BaseModel):
    kw: float = Field(50, gt=0, le=500)
    hours: float = Field(4, gt=0, le=8, description="energy = kW x hours")


@register("fix.battery", "fix", "Community battery at the far end",
          "Charges when voltage is high, gives back in the evening while there is headroom.", Battery)
def _battery(c: Controls, p: Battery) -> Controls:
    return c                       # the battery itself is placed by the runner (it needs the network)


def battery_spec(p: Battery, node: int) -> BatterySpec:
    return BatterySpec(kw=p.kw, kwh=p.kw * p.hours, node=node)
