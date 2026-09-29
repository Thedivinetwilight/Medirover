"""UTC time helpers. All timestamps in Medirover are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime

from shared.errors import PROTOCOL_INVALID, MediroverError


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MediroverError(
            f"invalid timestamp: {value!r}", code=PROTOCOL_INVALID, source="timeutil"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def age_seconds(dt: datetime, now: datetime | None = None) -> float:
    now = now or now_utc()
    return (now - dt).total_seconds()
