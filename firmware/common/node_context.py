"""Node configuration (validated; shared by all node types)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from shared.constants import (
    DEFAULT_HEARTBEAT_INTERVAL_S,
    DEFAULT_TELEMETRY_INTERVAL_S,
    FIRMWARE_VERSION,
)


class NodeConfig(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    node_name: str = Field(min_length=1, max_length=128)
    node_type: Literal["motion", "sensor", "hub"] = "motion"
    capabilities: list[str] = Field(default_factory=list)
    firmware_version: str = FIRMWARE_VERSION

    heartbeat_interval_s: float = Field(default=DEFAULT_HEARTBEAT_INTERVAL_S, gt=0)
    telemetry_interval_s: float = Field(default=DEFAULT_TELEMETRY_INTERVAL_S, gt=0)
    seed: int = 42

    # Motion-node scenario parameters (ignored by sensor nodes)
    drive_every_s: float = Field(default=15.0, ge=0)
    drive_duration_s: float = Field(default=3.0, gt=0)
    drive_speed_mps: float = Field(default=0.25, ge=0, le=1.0)
