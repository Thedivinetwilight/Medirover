"""Fault feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from backend.api.context import AppContext
from backend.api.deps import get_ctx_http
from backend.database.models import FaultRecord
from backend.schemas.api import FaultOut

router = APIRouter(prefix="/api/v1/faults", tags=["faults"])


@router.get("", response_model=list[FaultOut])
def list_faults(
    node_id: str | None = Query(default=None),
    open_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    ctx: AppContext = Depends(get_ctx_http),
) -> list[dict]:
    with ctx.sessions() as session:
        stmt = select(FaultRecord).order_by(FaultRecord.id.desc()).limit(limit)
        if node_id:
            stmt = stmt.where(FaultRecord.node_id == node_id)
        if open_only:
            stmt = stmt.where(FaultRecord.cleared_at.is_(None))
        rows = session.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "node_id": r.node_id,
            "fault_code": r.fault_code,
            "message": r.message,
            "detected_at": r.detected_at,
            "cleared_at": r.cleared_at,
            "metadata": r.metadata_,
        }
        for r in rows
    ]
