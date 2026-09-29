"""Message type registry: the only place that knows what types exist.

Adding a message type = one entry here + payload schema in shared.schemas.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from shared.schemas.node import (
    AckPayload,
    HeartbeatPayload,
    IdentifyPayload,
    PingPayload,
    RejectPayload,
    SubscribePayload,
    TelemetryPayload,
    WelcomePayload,
)
from shared.types import MessageDirection


class NodeMessageType(StrEnum):
    IDENTIFY = "identify"
    HEARTBEAT = "heartbeat"
    TELEMETRY = "telemetry"
    ACK = "ack"


class ServerMessageType(StrEnum):
    WELCOME = "welcome"
    REJECT = "reject"
    PING = "ping"


class ClientMessageType(StrEnum):
    STATE_SNAPSHOT = "state_snapshot"
    STATE_UPDATE = "state_update"
    EVENT = "event"
    PONG = "pong"


#: type -> (direction, payload model or None for empty payloads)
NODE_TO_BACKEND_TYPES: dict[str, tuple[MessageDirection, type | None]] = {
    NodeMessageType.IDENTIFY.value: (MessageDirection.NODE_TO_BACKEND, IdentifyPayload),
    NodeMessageType.HEARTBEAT.value: (MessageDirection.NODE_TO_BACKEND, HeartbeatPayload),
    NodeMessageType.TELEMETRY.value: (MessageDirection.NODE_TO_BACKEND, TelemetryPayload),
    NodeMessageType.ACK.value: (MessageDirection.NODE_TO_BACKEND, AckPayload),
}

BACKEND_TO_NODE_TYPES: dict[str, tuple[MessageDirection, type | None]] = {
    ServerMessageType.WELCOME.value: (MessageDirection.BACKEND_TO_NODE, WelcomePayload),
    ServerMessageType.REJECT.value: (MessageDirection.BACKEND_TO_NODE, RejectPayload),
    ServerMessageType.PING.value: (MessageDirection.BACKEND_TO_NODE, PingPayload),
}

BACKEND_TO_CLIENT_TYPES: dict[str, tuple[MessageDirection, type | None]] = {
    ClientMessageType.STATE_SNAPSHOT.value: (MessageDirection.BACKEND_TO_CLIENT, None),
    ClientMessageType.STATE_UPDATE.value: (MessageDirection.BACKEND_TO_CLIENT, None),
    ClientMessageType.EVENT.value: (MessageDirection.BACKEND_TO_CLIENT, None),
    ClientMessageType.PONG.value: (MessageDirection.BACKEND_TO_CLIENT, None),
}

CLIENT_TO_BACKEND_TYPES: dict[str, tuple[MessageDirection, type | None]] = {
    ClientMessageType.PONG.value: (MessageDirection.CLIENT_TO_BACKEND, None),
    "subscribe": (MessageDirection.CLIENT_TO_BACKEND, SubscribePayload),
    "ping": (MessageDirection.CLIENT_TO_BACKEND, None),
}


def known_message_types() -> list[str]:
    seen: dict[str, None] = {}
    for table in (
        NODE_TO_BACKEND_TYPES,
        BACKEND_TO_NODE_TYPES,
        BACKEND_TO_CLIENT_TYPES,
        CLIENT_TO_BACKEND_TYPES,
    ):
        for k in table:
            seen.setdefault(k, None)
    return sorted(seen)


def message_direction(message_type: str) -> MessageDirection | None:
    for table in (
        NODE_TO_BACKEND_TYPES,
        BACKEND_TO_NODE_TYPES,
        BACKEND_TO_CLIENT_TYPES,
        CLIENT_TO_BACKEND_TYPES,
    ):
        if message_type in table:
            return table[message_type][0]
    return None


def message_model(message_type: str) -> type[BaseModel] | None:
    for table in (
        NODE_TO_BACKEND_TYPES,
        BACKEND_TO_NODE_TYPES,
        BACKEND_TO_CLIENT_TYPES,
        CLIENT_TO_BACKEND_TYPES,
    ):
        if message_type in table:
            return table[message_type][1]  # type: ignore[return-value]
    return None


def is_known(message_type: str) -> bool:
    return message_direction(message_type) is not None
