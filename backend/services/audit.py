"""Audit trail helper (never crashes the caller)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.database.models import AuditRecord
from shared.utils.timeutil import now_utc, to_iso

logger = logging.getLogger("medirover.audit")


def record_audit(
    session_factory: sessionmaker[Session],
    *,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with session_factory() as session:
            session.add(
                AuditRecord(
                    ts=to_iso(now_utc()),
                    actor=actor,
                    action=action,
                    target=target,
                    details=details or {},
                )
            )
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("audit record failed: %s %s", actor, action)
