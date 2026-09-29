"""Configuration loading and validation (master directive §19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import (
    REPO_ROOT,
    Settings,
    load_environment_config,
)
from shared.errors import ConfigError, ConfigMissingError
from shared.types import Environment


def test_development_defaults_are_valid():
    settings = load_environment_config("development")
    assert settings.environment == Environment.DEVELOPMENT
    assert settings.port == 8000
    # relative sqlite path resolved against repo root
    assert settings.db_url.startswith("sqlite:///" + str(REPO_ROOT))
    assert settings.heartbeat_interval_s < settings.stale_after_s < settings.offline_after_s


def test_testing_env_requires_config_file(tmp_path: Path):
    with pytest.raises(ConfigMissingError):
        load_environment_config("testing", config_dir=tmp_path)


def test_invalid_config_rejected():
    with pytest.raises(ConfigError):
        Settings(
            environment=Environment.DEVELOPMENT,
            db_url="sqlite:////tmp/medirover-test-invalid.db",
            heartbeat_interval_s=5.0,
            stale_after_s=1.0,  # stale must exceed heartbeat
        )


def test_unknown_environment_rejected():
    with pytest.raises(ConfigError):
        load_environment_config("production")


def test_hardware_requires_ack(monkeypatch):
    monkeypatch.delenv("MEDIROVER_HARDWARE_ACK", raising=False)
    with pytest.raises(ConfigError):
        load_environment_config("hardware")
    monkeypatch.setenv("MEDIROVER_HARDWARE_ACK", "yes")
    settings = load_environment_config("hardware")
    assert settings.environment == Environment.HARDWARE


def test_env_var_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIROVER_PORT", "9911")
    monkeypatch.setenv("MEDIROVER_DB_URL", f"sqlite:///{tmp_path}/x.db")
    settings = load_environment_config("development")
    assert settings.port == 9911
    assert settings.db_url.endswith("x.db")
