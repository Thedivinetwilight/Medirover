"""Stateless frame validator: raw text -> exactly one explicit outcome.

Check order (first failure wins):
  1. JSON + envelope structure            -> MALFORMED
  2. protocol_version supported           -> PROTOCOL_VERSION_MISMATCH
  3. message_type known for this direction -> UNKNOWN_TYPE
  4. payload schema valid                 -> INVALID
  5. timestamp within skew limit          -> STALE
  6. node_id present (node->backend)      -> INVALID
  => VALID

Ordering/duplication (stateful) is checked by SequenceTracker, which the
connection handler applies after this validator returns VALID.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.constants import MAX_TIMESTAMP_SKEW_S, PROTOCOL_VERSION
from shared.protocols.codec import MalformedFrameError, decode_frame
from shared.protocols.registry import is_known, message_direction, message_model
from shared.schemas.envelope import Envelope, ValidationResult
from shared.types import MessageDirection, ValidationOutcome
from shared.utils.timeutil import now_utc


class FrameValidator:
    def __init__(
        self,
        direction: MessageDirection,
        supported_protocol_versions: tuple[int, ...] = (PROTOCOL_VERSION,),
        max_timestamp_skew_s: float = MAX_TIMESTAMP_SKEW_S,
    ) -> None:
        self.direction = direction
        self.supported_protocol_versions = set(supported_protocol_versions)
        self.max_timestamp_skew_s = max_timestamp_skew_s

    def validate(self, raw: str, *, now=None) -> ValidationResult:
        # 1. structure
        try:
            envelope = decode_frame(raw)
        except MalformedFrameError as exc:
            return ValidationResult.fail(
                ValidationOutcome.MALFORMED, code="PROTOCOL_MALFORMED", message=exc.message
            )

        # 2. protocol version
        if envelope.protocol_version not in self.supported_protocol_versions:
            return ValidationResult.fail(
                ValidationOutcome.PROTOCOL_VERSION_MISMATCH,
                code="PROTOCOL_VERSION_MISMATCH",
                message=(
                    f"protocol_version {envelope.protocol_version} not supported "
                    f"(supported: {sorted(self.supported_protocol_versions)})"
                ),
                envelope=envelope,
            )

        # 3. message type known & direction
        if not is_known(envelope.message_type):
            return ValidationResult.fail(
                ValidationOutcome.UNKNOWN_TYPE,
                code="PROTOCOL_UNKNOWN_TYPE",
                message=f"unknown message_type {envelope.message_type!r}",
                envelope=envelope,
            )
        actual = message_direction(envelope.message_type)
        if actual != self.direction:
            return ValidationResult.fail(
                ValidationOutcome.UNKNOWN_TYPE,
                code="PROTOCOL_UNKNOWN_TYPE",
                message=(
                    f"message_type {envelope.message_type!r} is not accepted "
                    f"on this channel (expected direction {self.direction.value})"
                ),
                envelope=envelope,
            )

        # 4. payload schema
        model = message_model(envelope.message_type)
        if model is not None:
            try:
                model.model_validate(envelope.payload)
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first.get("loc", ()))
                return ValidationResult.fail(
                    ValidationOutcome.INVALID,
                    code="PROTOCOL_INVALID",
                    message=f"payload invalid at {loc or '<root>'}: {first.get('msg')}",
                    envelope=envelope,
                )

        # 5. freshness
        now = now or now_utc()
        age = (now - envelope.timestamp).total_seconds()
        if age < -self.max_timestamp_skew_s or age > self.max_timestamp_skew_s:
            return ValidationResult.fail(
                ValidationOutcome.STALE,
                code="PROTOCOL_STALE",
                message=f"timestamp skew {age:.1f}s exceeds {self.max_timestamp_skew_s}s",
                envelope=envelope,
            )

        # 6. identity required on node-originated channels
        if self.direction in (MessageDirection.NODE_TO_BACKEND, MessageDirection.BACKEND_TO_NODE):
            if not envelope.node_id:
                return ValidationResult.fail(
                    ValidationOutcome.INVALID,
                    code="PROTOCOL_INVALID",
                    message="node_id must be non-empty on node channels",
                    envelope=envelope,
                )

        return ValidationResult.ok(envelope)


class EnvelopeBuilder(BaseModel):
    """Helper for constructing outbound frames with correct sequencing."""

    model_config = ConfigDict(frozen=True)
    direction: MessageDirection
    protocol_version: int = PROTOCOL_VERSION
    node_id: str = ""
    sequence: int = Field(default=-1, ge=-1)

    def next_sequence(self) -> int:
        self = self.model_copy(update={"sequence": self.sequence + 1})
        return self.sequence

    def build(self, message_type: str, payload: dict, *, now=None) -> Envelope:
        from shared.utils.ids import new_message_id
        from shared.utils.timeutil import now_utc

        return Envelope(
            protocol_version=self.protocol_version,
            message_version=1,
            message_type=message_type,
            message_id=new_message_id(),
            sequence=self.sequence + 1,
            timestamp=now or now_utc(),
            node_id=self.node_id,
            payload=payload,
        )
