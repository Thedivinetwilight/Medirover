"""Centralized configuration (master directive §19).

Precedence: defaults < config/{environment}.yaml < environment variables
(MEDIROVER_*). Validated at startup; hardware mode requires an explicit
acknowledgement. Secrets are never read from config files.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from shared.errors import ConfigError, ConfigMissingError
from shared.types import Environment

REPO_ROOT = Path(__file__).resolve().parents[1]

_ENV_PREFIX = "MEDIROVER_"


class DemoSettings(BaseModel):
    """Parameters for the simulated demo node (scripts/demo.py)."""

    node_id: str = "motion-01"
    node_name: str = "Medirover Motion Node (simulated)"
    drop_every_s: float = 30.0  # simulated link drop period
    drop_for_s: float = 4.0  # simulated link drop duration
    drive_every_s: float = 15.0  # self-issued demo drive cycle
    drive_duration_s: float = 3.0


class Settings(BaseModel):
    environment: Environment = Environment.DEVELOPMENT
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    db_url: str = ""

    heartbeat_interval_s: float = Field(default=1.0, gt=0)
    telemetry_interval_s: float = Field(default=1.0, gt=0)
    stale_after_s: float = Field(default=3.0, gt=0)
    offline_after_s: float = Field(default=10.0, gt=0)
    supervisor_scan_s: float = Field(default=0.2, gt=0)
    identify_timeout_s: float = Field(default=5.0, gt=0)

    max_frame_bytes: int = Field(default=16384, gt=0)
    frontend_dir: str = "frontend"
    log_level: str = "INFO"
    log_json: bool = True
    seed: int | None = 42

    demo: DemoSettings = Field(default_factory=DemoSettings)

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if not (self.heartbeat_interval_s < self.stale_after_s):
            raise ConfigError("stale_after_s must exceed heartbeat_interval_s")
        if not (self.stale_after_s < self.offline_after_s):
            raise ConfigError("offline_after_s must exceed stale_after_s")
        if not (self.supervisor_scan_s < self.stale_after_s / 2):
            raise ConfigError("supervisor_scan_s must be under stale_after_s/2")
        if not (self.telemetry_interval_s <= self.heartbeat_interval_s):
            raise ConfigError("telemetry_interval_s must be <= heartbeat_interval_s")
        # Normalize / create the SQLite location.
        # "sqlite:///data/x.db" is RELATIVE (the third slash is URL syntax);
        # "sqlite:////abs/x.db" (four slashes) is absolute.
        if self.db_url.startswith("sqlite:///"):
            rest = self.db_url[len("sqlite:///") :]
            if rest and not rest.startswith("/"):
                abs_path = (REPO_ROOT / rest).resolve()
                self.db_url = f"sqlite:///{abs_path}"
                Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        if not self.db_url:
            default = REPO_ROOT / "data" / f"medirover_{self.environment.value}.db"
            default.parent.mkdir(parents=True, exist_ok=True)
            self.db_url = f"sqlite:///{default}"
        # Resolve relative frontend dir against repo root
        if not Path(self.frontend_dir).is_absolute():
            self.frontend_dir = str(REPO_ROOT / self.frontend_dir)
        return self

    @property
    def frontend_path(self) -> Path:
        return Path(self.frontend_dir)


def _env_override(name: str) -> str | None:
    return os.environ.get(_ENV_PREFIX + name)


def load_environment_config(
    environment: Environment | str = Environment.DEVELOPMENT,
    *,
    config_dir: Path | None = None,
) -> Settings:
    """Load settings for an environment. Raises ConfigError/ConfigMissingError."""
    if isinstance(environment, str):
        try:
            environment = Environment(environment)
        except ValueError as exc:
            raise ConfigError(
                f"unknown environment {environment!r} (expected one of {[e.value for e in Environment]})"
            ) from exc

    if environment == Environment.HARDWARE:
        if os.environ.get(_ENV_PREFIX + "HARDWARE_ACK") != "yes":
            raise ConfigError(
                "hardware environment requires explicit acknowledgement: "
                "set MEDIROVER_HARDWARE_ACK=yes (see docs/SAFETY.md, docs/HARDWARE.md)"
            )

    config_dir = config_dir or (REPO_ROOT / "config")
    data: dict = {}
    yaml_path = config_dir / f"{environment.value}.yaml"
    if yaml_path.exists():
        loaded = yaml.safe_load(yaml_path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"config file {yaml_path} must contain a mapping")
        data = loaded
    else:
        # Absent config file is fine (defaults apply), but note it for testing env
        if environment == Environment.TESTING:
            raise ConfigMissingError(f"missing config file: {yaml_path}")

    # Environment variable overrides (scalar fields + demo.*)
    overrides: dict = {}
    for field_name in (
        "host",
        "port",
        "db_url",
        "heartbeat_interval_s",
        "telemetry_interval_s",
        "stale_after_s",
        "offline_after_s",
        "supervisor_scan_s",
        "identify_timeout_s",
        "max_frame_bytes",
        "log_level",
        "log_json",
        "seed",
    ):
        raw = _env_override(field_name.upper())
        if raw is not None:
            overrides[field_name] = raw
    if overrides:
        data = {**data, **overrides}

    try:
        return Settings(**data)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(
            f"invalid configuration for environment {environment.value}: {exc}",
            details={"environment": environment.value, "raw": data},
        ) from exc


def load_default_config() -> Settings:
    env_name = _env_override("ENVIRONMENT") or Environment.DEVELOPMENT.value
    return load_environment_config(env_name)
