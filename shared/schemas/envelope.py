"""The protocol envelope shared by every Medirover message (master directive §11).

    {
      "protocol_version": 1,
      "message_version": 1,
      "message_type": "heartbeat",
      "message_id": "<uuid4>",
      "sequence": 12,
      "timestamp": "2026-09-29T12:00:00.000000+00:00",
      "node_id": "motion-01",
      "payload": { ... }
    }

Rules:
- message_id is unique per message (dedup key).
- sequence is strictly increasing per connection session (starts at 0).
- timestamp is UTC ISO-8601; frames older than the skew limit are STALE.
- node_id may be empty only for backend->client messages.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.types import ValidationOutcome

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(ge=1, le=100)
    message_version: int = Field(ge=1, le=100)
    message_type: str = Field(min_length=1, max_length=64)
    message_id: str = Field(pattern=UUID_RE)
    sequence: int = Field(ge=0)
    timestamp: datetime
    node_id: str = Field(default="", max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message_type")
    @classmethod
    def _type_name(cls, v: str) -> str:
        if not v.isidentifier():
            raise ValueError("message_type must be a lowercase identifier")
        return v


class ValidationResult(BaseModel):
    """The result of validating one frame. Exactly one outcome, always."""

    outcome: ValidationOutcome
    envelope: Envelope | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.outcome == ValidationOutcome.VALID

    @classmethod
    def ok(cls, envelope: Envelope) -> ValidationResult:
        return cls(outcome=ValidationOutcome.VALID, envelope=envelope)

    @classmethod
    def fail(
        cls, outcome: ValidationOutcome, *, code: str, message: str, envelope: Envelope | None = None
    ) -> ValidationResult:
        return cls(
            outcome=outcome,
            envelope=envelope,
            error_code=code,
            error_message=message,
        )
