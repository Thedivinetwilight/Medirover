"""Node protocol client: speaks the node->backend side of the protocol.

Responsibilities:
- connect + identify (fresh sequence per connection session)
- wait for welcome (server-negotiated intervals) or reject
- heartbeat / telemetry emission at negotiated intervals
- handle server frames: welcome, reject (fatal for the session), ping (-> ack)
- deterministic reconnect with exponential backoff (no jitter, reproducible)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from firmware.common.node_context import NodeConfig
from firmware.hardware.interfaces import ICommunication
from shared.constants import (
    MESSAGE_VERSION,
    PROTOCOL_VERSION,
    RECONNECT_BACKOFF_INITIAL_S,
    RECONNECT_BACKOFF_MAX_S,
)
from shared.errors import COMMUNICATION_REJECTED, COMMUNICATION_TIMEOUT, MediroverError
from shared.protocols.codec import encode_frame
from shared.protocols.registry import (
    NodeMessageType,
    ServerMessageType,
)
from shared.protocols.validator import FrameValidator
from shared.schemas.envelope import Envelope
from shared.schemas.node import AckOutcome, AckPayload, IdentifyPayload
from shared.types import MessageDirection
from shared.utils.ids import new_message_id
from shared.utils.timeutil import now_utc


class NodeRejectedError(MediroverError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(
            f"server rejected: {code} ({reason})", code=COMMUNICATION_REJECTED, source="node-client"
        )
        self.reject_code = code
        self.reject_reason = reason


class LinkClosedError(MediroverError):
    def __init__(self) -> None:
        super().__init__("link closed by peer", code=COMMUNICATION_TIMEOUT, source="node-client")


@dataclass
class ClientSettings:
    heartbeat_interval_s: float = 1.0
    telemetry_interval_s: float = 1.0
    welcome_timeout_s: float = 5.0
    reconnect_backoff_initial_s: float = RECONNECT_BACKOFF_INITIAL_S
    reconnect_backoff_max_s: float = RECONNECT_BACKOFF_MAX_S


class NodeProtocolClient:
    def __init__(
        self,
        config: NodeConfig,
        transport: ICommunication,
        client_settings: ClientSettings | None = None,
        *,
        heartbeat_provider: Callable[[], dict],
        telemetry_provider: Callable[[], dict],
    ) -> None:
        self._config = config
        self._transport = transport
        self._settings = client_settings or ClientSettings(
            heartbeat_interval_s=config.heartbeat_interval_s,
            telemetry_interval_s=config.telemetry_interval_s,
        )
        self._heartbeat_provider = heartbeat_provider
        self._telemetry_provider = telemetry_provider
        self._validator = FrameValidator(MessageDirection.BACKEND_TO_NODE)
        self._seq = -1
        self._hb_interval = self._settings.heartbeat_interval_s
        self._telem_interval = self._settings.telemetry_interval_s
        self.connection_count = 0
        self.last_error: str | None = None
        self.log = logging.getLogger(f"medirover.node.{config.node_id}")

    # ------------------------------------------------------------------ frame

    def _frame(self, message_type: str, payload: dict) -> str:
        self._seq += 1
        envelope = Envelope(
            protocol_version=PROTOCOL_VERSION,
            message_version=MESSAGE_VERSION,
            message_type=message_type,
            message_id=new_message_id(),
            sequence=self._seq,
            timestamp=now_utc(),
            node_id=self._config.node_id,
            payload=payload,
        )
        return encode_frame(envelope)

    async def _send(self, message_type: str, payload: dict) -> None:
        await self._transport.send(self._frame(message_type, payload))

    # -------------------------------------------------------------------- run

    async def run(self, stop_event: asyncio.Event) -> None:
        backoff = self._settings.reconnect_backoff_initial_s
        while not stop_event.is_set():
            try:
                await self._transport.connect()
                self._seq = -1
                self.connection_count += 1
                self.last_error = None
                self.log.info("connected (attempt %d)", self.connection_count)
                await self._send(
                    NodeMessageType.IDENTIFY.value,
                    IdentifyPayload(
                        node_id=self._config.node_id,
                        node_name=self._config.node_name,
                        node_type=self._config.node_type,
                        firmware_version=self._config.firmware_version,
                        capabilities=self._config.capabilities,
                    ).model_dump(mode="json"),
                )
                await self._await_welcome()
                backoff = self._settings.reconnect_backoff_initial_s
                await self._run_session(stop_event)
            except NodeRejectedError as exc:
                self.last_error = f"rejected: {exc.reject_code} {exc.reject_reason}"
                self.log.error("server rejected connection: %s", self.last_error)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — reconnect on any link failure
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.log.warning("link error: %s (reconnect in %.1fs)", self.last_error, backoff)
            finally:
                await self._safe_close()
            if stop_event.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._settings.reconnect_backoff_max_s)
        self.log.info("client stopped (connections=%d)", self.connection_count)

    async def _await_welcome(self) -> None:
        deadline = now_utc().timestamp() + self._settings.welcome_timeout_s
        while True:
            remaining = deadline - now_utc().timestamp()
            if remaining <= 0:
                raise MediroverError(
                    "no welcome before timeout", code=COMMUNICATION_TIMEOUT, source="node-client"
                )
            frame = await asyncio.wait_for(self._transport.recv(), timeout=remaining)
            if frame is None:
                raise LinkClosedError()
            if self._handle_server_frame(frame) == "welcome":
                return

    async def _run_session(self, stop_event: asyncio.Event) -> None:
        async def heartbeat_loop() -> None:
            while not stop_event.is_set():
                await asyncio.sleep(self._hb_interval)
                if stop_event.is_set():
                    return
                await self._send(NodeMessageType.HEARTBEAT.value, self._heartbeat_provider())

        async def telemetry_loop() -> None:
            while not stop_event.is_set():
                await asyncio.sleep(self._telem_interval)
                if stop_event.is_set():
                    return
                await self._send(NodeMessageType.TELEMETRY.value, self._telemetry_provider())

        async def recv_loop() -> None:
            while not stop_event.is_set():
                frame = await self._transport.recv()
                if frame is None:
                    raise LinkClosedError()
                self._handle_server_frame(frame)

        tasks = [
            asyncio.create_task(heartbeat_loop(), name="hb"),
            asyncio.create_task(telemetry_loop(), name="telem"),
            asyncio.create_task(recv_loop(), name="recv"),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            self.log.info("session ended (errors=%s)", self.last_error)

    # ----------------------------------------------------------------- server

    def _handle_server_frame(self, raw: str) -> str:
        result = self._validator.validate(raw)
        if not result.is_valid:
            self.log.warning("bad server frame: %s: %s", result.outcome.value, result.error_message)
            return result.outcome.value
        env = result.envelope
        assert env is not None
        if env.message_type == ServerMessageType.WELCOME.value:
            self._hb_interval = env.payload.get("heartbeat_interval_s", self._settings.heartbeat_interval_s)
            self._telem_interval = env.payload.get(
                "telemetry_interval_s", self._settings.telemetry_interval_s
            )
            self.log.info("welcome: hb=%.2fs telem=%.2fs", self._hb_interval, self._telem_interval)
            return "welcome"
        if env.message_type == ServerMessageType.REJECT.value:
            raise NodeRejectedError(env.payload.get("error_code", "?"), env.payload.get("reason", "?"))
        if env.message_type == ServerMessageType.PING.value:
            asyncio.get_running_loop().create_task(
                self._send(
                    NodeMessageType.ACK.value,
                    AckPayload(
                        message_id=env.message_id, outcome=AckOutcome.ACCEPTED
                    ).model_dump(mode="json"),
                )
            )
            return "ping"
        self.log.debug("ignoring server frame type %s", env.message_type)
        return "other"

    async def _safe_close(self) -> None:
        try:
            await self._transport.close()
        except Exception:  # noqa: BLE001
            pass
