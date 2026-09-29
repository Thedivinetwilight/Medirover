"""WebSocket fan-out to frontend clients.

Publishes: state_snapshot (on connect), state_update, event, pong.
Client filters: empty set = all nodes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.services.ws_types import WebSocketLike
from shared.constants import MESSAGE_VERSION, PROTOCOL_VERSION
from shared.protocols.codec import encode_frame
from shared.protocols.registry import ClientMessageType
from shared.schemas.envelope import Envelope
from shared.utils.ids import new_message_id
from shared.utils.timeutil import now_utc

logger = logging.getLogger("medirover.broadcaster")


@dataclass
class _Subscription:
    ws: WebSocketLike
    node_filter: frozenset[str] | None  # None = all
    sequence: int = 0
    bad_frames: int = field(default=0)


class Broadcaster:
    def __init__(self) -> None:
        self._subs: dict[object, _Subscription] = {}

    def __len__(self) -> int:
        return len(self._subs)

    def register(self, ws: WebSocketLike, node_ids: set[str] | None = None) -> object:
        key = id(ws)
        self._subs[key] = _Subscription(ws=ws, node_filter=frozenset(node_ids) if node_ids else None)
        return key

    def set_filter(self, ws: object, node_ids: set[str]) -> None:
        sub = self._subs.get(id(ws))
        if sub is not None:
            sub.node_filter = frozenset(node_ids) if node_ids else None

    def matches(self, sub: _Subscription, node_id: str) -> bool:
        return sub.node_filter is None or node_id in sub.node_filter

    def _next_sequence(self, sub: _Subscription) -> int:
        sub.sequence += 1
        return sub.sequence

    def _frame(self, sub: _Subscription, message_type: str, node_id: str, payload: dict) -> str:
        envelope = Envelope(
            protocol_version=PROTOCOL_VERSION,
            message_version=MESSAGE_VERSION,
            message_type=message_type,
            message_id=new_message_id(),
            sequence=self._next_sequence(sub),
            timestamp=now_utc(),
            node_id=node_id,
            payload=payload,
        )
        return encode_frame(envelope)

    async def _send(self, sub: _Subscription, text: str) -> bool:
        try:
            await sub.ws.send_text(text)
            return True
        except Exception:  # noqa: BLE001 — client went away
            self._drop(sub)
            return False

    def _drop(self, sub: _Subscription) -> None:
        self._subs.pop(id(sub.ws), None)

    def mark_bad_frame(self, ws: object) -> int:
        sub = self._subs.get(id(ws))
        if sub is not None:
            sub.bad_frames += 1
            return sub.bad_frames
        return 0

    def unregister(self, ws: object) -> None:
        self._subs.pop(id(ws), None)

    async def send_snapshot(self, ws: object, nodes: list[dict], events: list) -> None:
        sub = self._subs.get(id(ws))
        if sub is None:
            return
        payload = {
            "nodes": nodes,
            "events": [e.to_dict() for e in events],
        }
        await self._send(sub, self._frame(sub, ClientMessageType.STATE_SNAPSHOT.value, "", payload))

    async def publish_state_update(self, node_id: str, state: dict) -> None:
        for sub in list(self._subs.values()):
            if self.matches(sub, node_id):
                await self._send(sub, self._frame(sub, ClientMessageType.STATE_UPDATE.value, node_id, state))

    async def publish_event(self, event) -> None:
        node_id = event.node_id or ""
        for sub in list(self._subs.values()):
            if node_id and not self.matches(sub, node_id):
                continue
            await self._send(sub, self._frame(sub, ClientMessageType.EVENT.value, node_id, event.to_dict()))

    async def send_pong(self, ws: object) -> None:
        sub = self._subs.get(id(ws))
        if sub is not None:
            await self._send(
                sub, self._frame(sub, ClientMessageType.PONG.value, "", {"at": now_utc().isoformat()})
            )

    async def close_all(self) -> None:
        for sub in list(self._subs.values()):
            try:
                await sub.ws.close(code=1001)
            except Exception:  # noqa: BLE001
                pass
        self._subs.clear()
