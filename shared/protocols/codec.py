"""Frame codec: JSON encode/decode of envelopes (deterministic bytes)."""

from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from shared.errors import PROTOCOL_MALFORMED, MediroverError
from shared.schemas.envelope import Envelope

_ADAPTER: TypeAdapter = TypeAdapter(Envelope)


class MalformedFrameError(MediroverError):
    """Raised when raw text cannot be parsed into a valid envelope at all."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message, code=PROTOCOL_MALFORMED, source="codec", details=details)


def encode_frame(envelope: Envelope) -> str:
    return json.dumps(
        envelope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def decode_frame(raw: str) -> Envelope:
    """Parse raw text into an Envelope or raise MalformedFrameError."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MalformedFrameError(f"frame is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MalformedFrameError("frame must be a JSON object")
    try:
        return _ADAPTER.validate_python(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        raise MalformedFrameError(
            f"envelope invalid at {loc or '<root>'}: {first.get('msg')}",
            details={"field": loc, "msg": str(first.get("msg"))},
        ) from exc
