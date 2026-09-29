"""SQLAlchemy 2.0 models.

Separation of concerns (master directive §14):
- Node               -> node registry / configuration
- NodeRuntimeState   -> live runtime state (one row per node, upserted)
- TelemetryReading   -> historical telemetry (append-only)
- EventRecord        -> structured events (bounded by retention)
- FaultRecord        -> safety/operational faults
- AuditRecord        -> operator/system audit trail

Timestamps are stored as ISO-8601 UTC strings (explicit, unambiguous).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Node(Base):
    """Node registry. node_id is the stable identity chosen by the node."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    node_type: Mapped[str] = mapped_column(String(16))
    firmware_version: Mapped[str] = mapped_column(String(32))
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[str] = mapped_column(String(40))
    last_identified_at: Mapped[str] = mapped_column(String(40))

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "firmware_version": self.firmware_version,
            "capabilities": list(self.capabilities or []),
            "first_seen_at": self.first_seen_at,
            "last_identified_at": self.last_identified_at,
        }


class NodeRuntimeState(Base):
    """Live runtime view. Exactly one row per node; upserted, never appended."""

    __tablename__ = "node_runtime_state"

    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    connectivity: Mapped[str] = mapped_column(String(16), default="DISCONNECTED")
    safety_state: Mapped[str] = mapped_column(String(20), default="SAFE")
    source_kind: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    last_heartbeat_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_message_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    battery_voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_s: Mapped[float] = mapped_column(Float, default=0.0)
    last_telemetry: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[str] = mapped_column(String(40))


class TelemetryReading(Base):
    """Append-only telemetry history. (node_id, message_id, sensor_id) is
    unique so replayed/duplicated messages cannot duplicate rows."""

    __tablename__ = "telemetry_readings"
    __table_args__ = (
        UniqueConstraint("node_id", "message_id", "sensor_id", name="uq_telemetry_dedup"),
        Index("ix_telemetry_node_time", "node_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), ForeignKey("nodes.id"))
    message_id: Mapped[str] = mapped_column(String(36))
    sensor_id: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    quality: Mapped[str] = mapped_column(String(8), default="ok")
    received_at: Mapped[str] = mapped_column(String(40))


class EventRecord(Base):
    """Structured events (master directive §17). Bounded by retention."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_time", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(64))
    node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class FaultRecord(Base):
    __tablename__ = "faults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fault_code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[str] = mapped_column(String(40))
    cleared_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class AuditRecord(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
