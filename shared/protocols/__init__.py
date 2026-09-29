"""Communication protocol foundation (master directive §11).

The protocol is transport-agnostic: messages are JSON frames with a fixed
envelope, validated per direction before anything touches application state.
v0.1 transport: WebSocket (one JSON object per frame).
"""

from shared.protocols.codec import MalformedFrameError, decode_frame, encode_frame
from shared.protocols.registry import (
    CLIENT_TO_BACKEND_TYPES,
    NODE_TO_BACKEND_TYPES,
    ServerMessageType,
    known_message_types,
    message_direction,
    message_model,
)
from shared.protocols.sequence import SequenceTracker
from shared.protocols.validator import FrameValidator

__all__ = [
    "MalformedFrameError",
    "decode_frame",
    "encode_frame",
    "FrameValidator",
    "SequenceTracker",
    "NODE_TO_BACKEND_TYPES",
    "CLIENT_TO_BACKEND_TYPES",
    "ServerMessageType",
    "message_model",
    "message_direction",
    "known_message_types",
]
