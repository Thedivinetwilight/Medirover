"""Structured events (master directive §17).

One compact event model, bounded retention, no one-file-per-event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.types import Severity

from ..utils.timeutil import now_utc


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    source: str
    node_id: str | None = None
    event_type: str
    severity: Severity = Severity.INFO
    message: str
    correlation_id: str | None = None
    sequence: int | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        source: str,
        message: str,
        node_id: str | None = None,
        severity: Severity = Severity.INFO,
        correlation_id: str | None = None,
        state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> Event:
        return cls(
            timestamp=timestamp or now_utc(),
            source=source,
            node_id=node_id,
            event_type=event_type,
            severity=severity,
            message=message,
            correlation_id=correlation_id,
            state=state or {},
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def new_correlation_id() -> str:
    return uuid.uuid4().hex
