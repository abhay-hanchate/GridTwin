"""Environment settings for API v2 (plan section 13). Every variable is optional; defaults suit local development."""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def _git_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


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
    code_version: str = Field(default_factory=_git_version)  # part of every cache key
    max_body_bytes: int = 1_000_000
    rate_limit_per_minute: int = 30
    rate_limited_paths: tuple[str, ...] = ("/whatif", "/connection-check")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
