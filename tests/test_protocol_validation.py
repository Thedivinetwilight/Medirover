"""Known-answer protocol validation tests (directive §11, §21).

Deterministic: fixed frames, fixed 'now', fixed skew. No randomness.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from shared.protocols.codec import encode_frame
from shared.protocols.sequence import SequenceTracker
from shared.protocols.validator import FrameValidator
from shared.schemas.envelope import Envelope
from shared.types import MessageDirection, ValidationOutcome
from shared.utils.timeutil import now_utc

VALIDATOR = FrameValidator(MessageDirection.NODE_TO_BACKEND, max_timestamp_skew_s=30.0)
NOW = now_utc()


def frame(
    message_type: str = "heartbeat",
    node_id: str = "n1",
    payload: dict | None = None,
    protocol_version: int = 1,
    sequence: int = 1,
    message_id: str = "11111111-2222-3333-4444-555555555555",
    ts: str | None = None,
) -> str:
    envelope = Envelope(
        protocol_version=protocol_version,
        message_version=1,
        message_type=message_type,
        message_id=message_id,
        sequence=sequence,
        timestamp=ts or NOW,
        node_id=node_id,
        payload=payload or {"safety_state": "READY", "uptime_s": 1.0},
    )
    return encode_frame(envelope)


def test_valid_frame():
    result = VALIDATOR.validate(frame(), now=NOW)
    assert result.is_valid
    assert result.outcome == ValidationOutcome.VALID
    assert result.envelope is not None
    assert result.envelope.message_type == "heartbeat"


@pytest.mark.parametrize(
    "raw,expected_code",
    [
        ("not json at all", "MALFORMED"),
        ("[1,2,3]", "MALFORMED"),
        ('{"protocol_version": 1}', "MALFORMED"),  # missing required fields
        (
            '{"protocol_version":"x","message_version":1,"message_type":"heartbeat",'
            '"message_id":"bad","sequence":1,"timestamp":"2026-01-01T00:00:00+00:00",'
            '"node_id":"n1","payload":{}}',
            "MALFORMED",
        ),
    ],
)
def test_malformed_frames(raw: str, expected_code: str):
    result = VALIDATOR.validate(raw, now=NOW)
    assert result.outcome == ValidationOutcome.MALFORMED
    assert result.error_code == "PROTOCOL_MALFORMED"
    assert result.envelope is None


def test_protocol_version_mismatch():
    result = VALIDATOR.validate(frame(protocol_version=99), now=NOW)
    assert result.outcome == ValidationOutcome.PROTOCOL_VERSION_MISMATCH


def test_unknown_message_type():
    result = VALIDATOR.validate(frame(message_type="self_destruct"), now=NOW)
    assert result.outcome == ValidationOutcome.UNKNOWN_TYPE


def test_wrong_direction_type_rejected():
    # "welcome" is a backend->node type; a node channel must reject it
    result = VALIDATOR.validate(
        frame(
            message_type="welcome",
            payload={
                "accepted": True,
                "node_id": "n1",
                "server_time": "2026-01-01T00:00:00+00:00",
                "heartbeat_interval_s": 1.0,
                "telemetry_interval_s": 1.0,
            },
        ),
        now=NOW,
    )
    assert result.outcome == ValidationOutcome.UNKNOWN_TYPE


def test_invalid_payload():
    result = VALIDATOR.validate(frame(payload={"safety_state": "NOT_A_STATE", "uptime_s": 1.0}), now=NOW)
    assert result.outcome == ValidationOutcome.INVALID
    assert result.error_code == "PROTOCOL_INVALID"


def test_negative_uptime_rejected():
    result = VALIDATOR.validate(frame(payload={"safety_state": "READY", "uptime_s": -5.0}), now=NOW)
    assert result.outcome == ValidationOutcome.INVALID


def test_stale_timestamp():
    old = (NOW - timedelta(seconds=120)).isoformat()
    result = VALIDATOR.validate(frame(ts=old), now=NOW)
    assert result.outcome == ValidationOutcome.STALE


def test_future_timestamp_beyond_skew():
    future = (NOW + timedelta(seconds=120)).isoformat()
    result = VALIDATOR.validate(frame(ts=future), now=NOW)
    assert result.outcome == ValidationOutcome.STALE


def test_small_clock_skew_accepted():
    near = (NOW + timedelta(seconds=10)).isoformat()
    result = VALIDATOR.validate(frame(ts=near), now=NOW)
    assert result.is_valid


def test_empty_node_id_rejected_on_node_channel():
    result = VALIDATOR.validate(frame(node_id=""), now=NOW)
    assert result.outcome == ValidationOutcome.INVALID


def test_sequence_tracker():
    tracker = SequenceTracker()
    assert tracker.check("a", 0) == ValidationOutcome.VALID
    tracker.record("a", 0)
    assert tracker.check("b", 1) == ValidationOutcome.VALID
    tracker.record("b", 1)
    assert tracker.check("a", 2) == ValidationOutcome.DUPLICATE  # seen id
    assert tracker.check("c", 1) == ValidationOutcome.OUT_OF_ORDER  # <= last
    assert tracker.check("d", 5) == ValidationOutcome.VALID
    tracker.reset()
    assert tracker.check("e", 0) == ValidationOutcome.VALID


def test_sequence_window_bounded():
    tracker = SequenceTracker(max_seen=3)
    for i, cid in enumerate(["a", "b", "c", "d"]):
        assert tracker.check(cid, i) == ValidationOutcome.VALID
        tracker.record(cid, i)
    # 'a' fell out of the window -> no longer a duplicate
    assert tracker.check("a", 10) == ValidationOutcome.VALID
