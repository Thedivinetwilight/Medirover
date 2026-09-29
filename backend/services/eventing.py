"""Structured event service: persist + broadcast + bounded recent ring.

Two entry points:
- record_sync(): safe to call from synchronous code (broadcast scheduled)
- record(): async convenience (broadcast awaited)
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from backend.database.models import EventRecord
from backend.services.ws_types import EventPublisher
from shared.constants import (
    EVENT_RETENTION_S,
    MAX_EVENT_ROWS_RETAINED,
    MAX_STORED_EVENTS_FRONTEND,
)
from shared.events import Event
from shared.types import Severity
from shared.utils.asyncutil import schedule
from shared.utils.timeutil import now_utc, to_iso

logger = logging.getLogger("medirover.events")


class EventingService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        broadcaster: EventPublisher,  # Broadcaster (avoids circular import at module load)
    ) -> None:
        self._sessions = session_factory
        self._broadcaster = broadcaster
        self.recent: deque[Event] = deque(maxlen=MAX_STORED_EVENTS_FRONTEND)

    def record_sync(
        self,
        event_type: str,
        *,
        source: str,
        message: str,
        node_id: str | None = None,
        severity: Severity = Severity.INFO,
        state: dict | None = None,
        metadata: dict | None = None,
        persist: bool = True,
    ) -> Event:
        event = Event.create(
            event_type,
            source=source,
            message=message,
            node_id=node_id,
            severity=severity,
            state=state,
            metadata=metadata,
        )
        self.recent.append(event)
        if persist:
            self._persist(event)
        schedule(self._broadcaster.publish_event(event))
        return event

    async def record(
        self,
        event_type: str,
        *,
        source: str,
        message: str,
        node_id: str | None = None,
        severity: Severity = Severity.INFO,
        state: dict | None = None,
        metadata: dict | None = None,
        persist: bool = True,
    ) -> Event:
        event = self.record_sync(
            event_type,
            source=source,
            message=message,
            node_id=node_id,
            severity=severity,
            state=state,
            metadata=metadata,
            persist=persist,
        )
        await self._broadcaster.publish_event(event)
        return event

    def _persist(self, event: Event) -> None:
        try:
            with self._sessions() as session:
                session.add(
                    EventRecord(
                        timestamp=to_iso(event.timestamp),
                        source=event.source,
                        node_id=event.node_id,
                        event_type=event.event_type,
                        severity=event.severity.value,
                        message=event.message,
                        correlation_id=event.correlation_id,
                        sequence=event.sequence,
                        state=event.state,
                        metadata_=event.metadata,
                    )
                )
                session.commit()
        except Exception:  # noqa: BLE001 — event persistence must never kill a path
            logger.exception("failed to persist event %s", event.event_type)

    def prune(self, *, now=None) -> int:
        """Bounded retention (master directive §17). Returns rows removed."""
        now = now or now_utc()
        removed = 0
        try:
            with self._sessions() as session:
                cutoff = to_iso(now - timedelta(seconds=EVENT_RETENTION_S))
                pruned = session.execute(delete(EventRecord).where(EventRecord.timestamp < cutoff))
                removed += cast(CursorResult, pruned).rowcount or 0
                ids = (
                    session.execute(
                        select(EventRecord.id).order_by(EventRecord.id.desc()).offset(MAX_EVENT_ROWS_RETAINED)
                    )
                    .scalars()
                    .all()
                )
                if ids:
                    capped = session.execute(delete(EventRecord).where(EventRecord.id.in_(ids)))
                    removed += cast(CursorResult, capped).rowcount or 0
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("event retention prune failed")
        return removed

    def recent_events(self, node_id: str | None = None, limit: int = 100) -> list[Event]:
        items = [e for e in self.recent if node_id is None or e.node_id == node_id]
        return list(reversed(items[-limit:]))
