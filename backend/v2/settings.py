"""Environment settings for API v2 (plan section 13). Every variable is optional; defaults suit local development."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
RESULT_SOURCES = ("engine", "backend/v2/compute.py", "data/results/risk_calibration_pm10.json",
                  "data/results/risk_calibration_up_2005.json")
# Presentation code: changing it never changes a computed number, so it must not invalidate the precomputed results.
# Routes that do depend on one of these (e.g. /whatif on the registry) add that file's own hash to their cache key.
NOT_RESULTS = {"engine/registry.py", "engine/explain.py", "engine/report.py", "engine/onboard.py"}
NOT_RESULTS_DIRS = ("engine/explain_templates", "engine/report_templates")
CRLF, LF = bytes([13, 10]), bytes([10])


def results_version(root: Path = ROOT) -> str:
    """Hash of the code and rule data that produce the numbers (engine/ and the compute module).

    Used in every cache key: a change to that code invalidates cached results, while a docs or UI commit does not.
    Line endings are normalised so Windows and Linux checkouts agree.
    """
    digest = hashlib.sha256()
    for source in RESULT_SOURCES:
        base = root / source
        files = sorted(base.rglob("*")) if base.is_dir() else [base] if base.exists() else []
        for f in files:
            rel = f.relative_to(root).as_posix()
            if rel in NOT_RESULTS or rel.startswith(NOT_RESULTS_DIRS) or rel == "engine/reliability.py":
                continue
            if f.is_file() and f.suffix in (".py", ".json") and "__pycache__" not in f.parts:
                digest.update(rel.encode())
                digest.update(f.read_bytes().replace(CRLF, LF))
    return digest.hexdigest()[:12]


def file_version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(CRLF, LF)).hexdigest()[:12]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRIDTWIN_", extra="ignore")

    env: str = "dev"                                       # dev, test or prod
    data_dir: Path = ROOT / "data" / "processed"
    results_dir: Path = ROOT / "data" / "results"
    model_dir: Path = ROOT / "ml" / "models"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    offline: bool = False                                  # serve only the bundled precomputed results
    log_level: str = "INFO"
    rule_default: str = "up_2005"
    # Days after today the live day-ahead forecast can cover. Checked 10 Oct 2026: the five-model Open-Meteo request
    # had the three models it needs up to 8 days ahead and failed from 10; 7 keeps a margin.
    live_horizon_days: int = 7
    code_version: str = Field(default_factory=results_version)  # part of every cache key
    max_body_bytes: int = 1_000_000
    rate_limit_per_minute: int = 30
    rate_limited_paths: tuple[str, ...] = ("/whatif", "/connection-check")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
