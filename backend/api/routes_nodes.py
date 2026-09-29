"""Node endpoints: registry, live state, telemetry history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from backend.api.context import AppContext
from backend.api.deps import get_ctx_http
from backend.database.models import EventRecord, Node, TelemetryReading
from backend.schemas.api import (
    EventOut,
    NodeDetail,
    NodeSummary,
    TelemetryReadingOut,
)
from shared.errors import NOT_FOUND, MediroverError

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


def _require_node(ctx: AppContext, node_id: str) -> None:
    with ctx.sessions() as session:
        if session.get(Node, node_id) is None:
            raise MediroverError(f"node {node_id!r} not found", code=NOT_FOUND, source="api")


@router.get("", response_model=list[NodeSummary])
def list_nodes(ctx: AppContext = Depends(get_ctx_http)) -> list[dict]:
    return ctx.node_manager.node_summaries()


@router.get("/{node_id}", response_model=NodeDetail)
def get_node(node_id: str, ctx: AppContext = Depends(get_ctx_http)) -> dict:
    _require_node(ctx, node_id)
    summary = next((s for s in ctx.node_manager.node_summaries() if s["node_id"] == node_id), None)
    if summary is None:
        raise MediroverError(f"node {node_id!r} not found", code=NOT_FOUND, source="api")
    recent = len([e for e in ctx.eventing.recent_events(node_id, 200)])
    return {"node": summary, "recent_events": recent}


@router.get("/{node_id}/telemetry", response_model=list[TelemetryReadingOut])
def get_telemetry(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    sensor_id: str | None = Query(default=None),
    ctx: AppContext = Depends(get_ctx_http),
) -> list[dict]:
    _require_node(ctx, node_id)
    with ctx.sessions() as session:
        stmt = (
            select(TelemetryReading)
            .where(TelemetryReading.node_id == node_id)
            .order_by(TelemetryReading.id.desc())
            .limit(limit)
        )
        if sensor_id:
            stmt = stmt.where(TelemetryReading.sensor_id == sensor_id)
        rows = session.scalars(stmt).all()
    return [
        {
            "node_id": r.node_id,
            "sensor_id": r.sensor_id,
            "value": r.value,
            "unit": r.unit,
            "quality": r.quality,
            "message_id": r.message_id,
            "received_at": r.received_at,
        }
        for r in rows
    ]


@router.get("/{node_id}/events", response_model=list[EventOut])
def get_node_events(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    ctx: AppContext = Depends(get_ctx_http),
) -> list[dict]:
    _require_node(ctx, node_id)
    with ctx.sessions() as session:
        rows = session.scalars(
            select(EventRecord)
            .where(EventRecord.node_id == node_id)
            .order_by(EventRecord.id.desc())
            .limit(limit)
        ).all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "source": r.source,
            "node_id": r.node_id,
            "event_type": r.event_type,
            "severity": r.severity,
            "message": r.message,
            "correlation_id": r.correlation_id,
            "sequence": r.sequence,
            "state": r.state,
            "metadata": r.metadata_,
        }
        for r in rows
    ]
