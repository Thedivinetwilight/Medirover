"""Payload schemas for node<->backend protocol messages (v0.1).

Node -> backend: identify, heartbeat, telemetry, ack
Backend -> node: welcome, reject, ping
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.constants import FIRMWARE_VERSION, MAX_TELEMETRY_SAMPLES
from shared.types import SafetyState


class IdentifyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=64)
    node_name: str = Field(min_length=1, max_length=128)
    node_type: Literal["motion", "sensor", "hub"]
    firmware_version: str = Field(default=FIRMWARE_VERSION, min_length=1, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=32)


class HeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safety_state: SafetyState
    uptime_s: float = Field(ge=0)
    battery_voltage: float | None = Field(default=None, ge=0, le=60)


class TelemetrySample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_id: str = Field(min_length=1, max_length=64)
    value: float
    unit: str = Field(min_length=1, max_length=16)
    quality: Literal["ok", "degraded"] = "ok"


class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int = Field(ge=0)
    samples: list[TelemetrySample] = Field(min_length=1, max_length=MAX_TELEMETRY_SAMPLES)


class AckOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str  # id of the server message being acknowledged
    outcome: AckOutcome = AckOutcome.ACCEPTED
    note: str | None = Field(default=None, max_length=128)


class WelcomePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool = True
    node_id: str
    server_time: datetime
    heartbeat_interval_s: float = Field(gt=0)
    telemetry_interval_s: float = Field(gt=0)


class RejectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=128)
    error_code: str = Field(min_length=1, max_length=64)
    message_id: str | None = None  # id of the offending frame, when known


class PingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=128)


class SubscribePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_ids: list[str] = Field(default_factory=list)  # empty = all nodes
