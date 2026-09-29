"""Telemetry ingestion with DB-level idempotency (master directive §24).

Replayed or duplicated frames cannot create duplicate rows: the unique
constraint (node_id, message_id, sensor_id) makes inserts idempotent.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from backend.database.models import TelemetryReading
from shared.schemas.node import TelemetryPayload


def ingest(
    session: Session, node_id: str, message_id: str, payload: TelemetryPayload, received_at: str
) -> int:
    """Insert telemetry rows; returns the number of rows actually inserted."""
    rows = [
        {
            "node_id": node_id,
            "message_id": message_id,
            "sensor_id": s.sensor_id,
            "value": s.value,
            "unit": s.unit,
            "quality": s.quality,
            "received_at": received_at,
        }
        for s in payload.samples
    ]
    stmt = sqlite_insert(TelemetryReading).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["node_id", "message_id", "sensor_id"])
    result = cast(CursorResult, session.execute(stmt))
    session.commit()
    return result.rowcount or 0
