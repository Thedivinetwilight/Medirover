"""Fake backend endpoint for firmware tests (server side of MemoryLink).

Speaks the backend->node side of the protocol: welcome after identify,
records heartbeats/telemetry/acks. NOT used in the E2E tests (those use
the real backend over real WebSockets).
"""

from __future__ import annotations

import asyncio

from firmware.communication.simulated_transport import _MemoryEnd
from shared.constants import MESSAGE_VERSION, PROTOCOL_VERSION
from shared.protocols.codec import encode_frame
from shared.protocols.registry import ServerMessageType
from shared.protocols.sequence import SequenceTracker
from shared.protocols.validator import FrameValidator
from shared.schemas.envelope import Envelope
from shared.schemas.node import WelcomePayload
from shared.types import MessageDirection, ValidationOutcome
from shared.utils.ids import new_message_id
from shared.utils.timeutil import now_utc


class FakeBackend:
    def __init__(
        self,
        end: _MemoryEnd,
        *,
        heartbeat_interval_s: float = 0.1,
        telemetry_interval_s: float = 0.05,
    ) -> None:
        self.end = end
        self.heartbeat_interval_s = heartbeat_interval_s
        self.telemetry_interval_s = telemetry_interval_s
        self.validator = FrameValidator(MessageDirection.NODE_TO_BACKEND)
        self.identify: dict | None = None
        self.identify_count = 0
        self.heartbeats: list[dict] = []
        self.telemetry: list[dict] = []
        self.acks: list[tuple[dict, str]] = []
        self.invalid_count = 0
        self._tracker = SequenceTracker()

    def _server_frame(self, message_type: str, payload: dict, node_id: str, message_id: str) -> str:
        return encode_frame(
            Envelope(
                protocol_version=PROTOCOL_VERSION,
                message_version=MESSAGE_VERSION,
                message_type=message_type,
                message_id=message_id,
                sequence=0,
                timestamp=now_utc(),
                node_id=node_id,
                payload=payload,
            )
        )

    async def send_welcome(self, node_id: str) -> None:
        await self.end.send(
            self._server_frame(
                ServerMessageType.WELCOME.value,
                WelcomePayload(
                    accepted=True,
                    node_id=node_id,
                    server_time=now_utc(),
                    heartbeat_interval_s=self.heartbeat_interval_s,
                    telemetry_interval_s=self.telemetry_interval_s,
                ).model_dump(mode="json"),
                node_id,
                new_message_id(),
            )
        )

    async def send_ping(self) -> str:
        """Send a ping; returns the ping's message_id (for ack assertions)."""
        ping_id = new_message_id()
        node_id = self.identify["node_id"] if self.identify else ""
        await self.end.send(
            self._server_frame(
                ServerMessageType.PING.value,
                {"note": "link check"},
                node_id,
                ping_id,
            )
        )
        return ping_id

    async def run(self, stop_event: asyncio.Event) -> None:
        await self.end.connect()
        while not stop_event.is_set():
            try:
                frame = await asyncio.wait_for(self.end.recv(), timeout=0.2)
            except TimeoutError:
                continue
            if frame is None:
                return
            result = self.validator.validate(frame)
            if not result.is_valid:
                self.invalid_count += 1
                continue
            env = result.envelope
            assert env is not None

            # identify starts a fresh connection session (sequence restarts)
            if env.message_type == "identify":
                self._tracker.reset()
                self._tracker.record(env.message_id, env.sequence)
                self.identify = env.payload
                self.identify_count += 1
                await self.send_welcome(env.node_id)
                continue

            order = self._tracker.check(env.message_id, env.sequence)
            if order == ValidationOutcome.DUPLICATE:
                continue
            if order == ValidationOutcome.OUT_OF_ORDER:
                continue
            self._tracker.record(env.message_id, env.sequence)
            if env.message_type == "heartbeat":
                self.heartbeats.append(env.payload)
            elif env.message_type == "telemetry":
                self.telemetry.append(env.payload)
            elif env.message_type == "ack":
                self.acks.append((env.payload, env.message_id))
