"""Global event feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from backend.api.context import AppContext
from backend.api.deps import get_ctx_http
from backend.database.models import EventRecord
from backend.schemas.api import EventOut

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    limit: int = Query(default=100, ge=1, le=1000),
    node_id: str | None = Query(default=None),
    ctx: AppContext = Depends(get_ctx_http),
) -> list[dict]:
    with ctx.sessions() as session:
        stmt = select(EventRecord).order_by(EventRecord.id.desc()).limit(limit)
        if node_id:
            stmt = stmt.where(EventRecord.node_id == node_id)
        rows = session.scalars(stmt).all()
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
