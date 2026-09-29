"""Pydantic contracts for Person 2 ML and operational-readiness API routes."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WarningCase(BaseModel):
    violation_steps: int
    max_vm_pu: float
    first_unsafe: str | None
    unsafe_times: list[str]


class EarlyWarningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    risk_band: str
    demand_mode: str
    demand_proxy_date: str
    pv_share: float
    band: str
    cases: dict[str, WarningCase]
    predicted: WarningCase
    reference: WarningCase
    provenance: dict[str, str]


class FeatureImportance(BaseModel):
    feature: str
    definition: str
    gain_normalized: float
    permutation_mae_increase: float


class ModelReportResponse(BaseModel):
    model: str
    generated_at: str
    evaluation_period: str
    features_available_at_issue_time: bool
    importance: list[FeatureImportance]
    limitations: list[str]


class ReadinessResponse(BaseModel):
    status: str
    ready: bool
    files: dict[str, bool]


class LiveForecastPoint(BaseModel):
    t: str
    p10: float
    p50: float
    p90: float


class LiveForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    unit: str
    date: str
    generated_at: str
    weather_source: str
    weather_url: str
    model: str
    points: list[LiveForecastPoint]


class SolarCaused(BaseModel):
    """Unsafe intervals that appear only because of solar (unsafe with it, safe without it)."""

    violation_steps: int
    first_unsafe: str | None
    unsafe_times: list[str]


class LiveWarningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    risk_band: str
    demand_mode: str
    demand_proxy_date: str
    pv_share: float
    band: str
    cases: dict[str, WarningCase]
    predicted: WarningCase
    without_solar: WarningCase
    solar_caused: SolarCaused
    provenance: dict[str, str]
