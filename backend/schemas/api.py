"""API response models. The API never exposes ORM objects directly."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.constants import PROTOCOL_VERSION
from shared.types import Environment, SourceKind


class ErrorBody(BaseModel):
    code: str
    message: str
    category: str
    severity: str
    source: str
    recoverable: bool
    recommended_action: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: Environment
    source_kind: SourceKind
    protocol_version: int = PROTOCOL_VERSION
    server_time: str
    database: str = "ok"


class TelemetryValue(BaseModel):
    value: float
    unit: str
    quality: str = "ok"
    at: str | None = None


class NodeStateResponse(BaseModel):
    node_id: str
    connectivity: str
    safety_state: str
    source_kind: SourceKind
    last_heartbeat_at: str | None = None
    last_message_at: str | None = None
    last_sequence: int = 0
    battery_voltage: float | None = None
    uptime_s: float = 0.0
    last_telemetry: dict[str, TelemetryValue] = Field(default_factory=dict)
    updated_at: str | None = None


class NodeSummary(BaseModel):
    node_id: str
    name: str
    node_type: str
    firmware_version: str
    capabilities: list[str] = Field(default_factory=list)
    first_seen_at: str | None = None
    last_identified_at: str | None = None
    state: NodeStateResponse


class NodeDetail(BaseModel):
    node: NodeSummary
    recent_events: int = 0


class TelemetryReadingOut(BaseModel):
    node_id: str
    sensor_id: str
    value: float
    unit: str
    quality: str
    message_id: str
    received_at: str


class EventOut(BaseModel):
    id: int
    timestamp: str
    source: str
    node_id: str | None
    event_type: str
    severity: str
    message: str
    correlation_id: str | None = None
    sequence: int | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FaultOut(BaseModel):
    id: int
    node_id: str | None
    fault_code: str
    message: str
    detected_at: str
    cleared_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
