"""Pydantic response models for API v2 (shapes agreed with the dashboard in frontend/src/api/v2types.ts)."""
from __future__ import annotations

from pydantic import BaseModel


class Rule(BaseModel):
    id: str
    label: str
    vmin_v: float
    vmax_v: float
    vmin_pu: float
    vmax_pu: float
    nominal_v: float
    region: str
    source: str
    verification: str              # primary, secondary or unverified
    note: str = ""


class Health(BaseModel):
    status: str
    version: str
    env: str


class Readiness(BaseModel):
    ready: bool
    mode: str                      # online or offline
    checks: dict[str, bool]
