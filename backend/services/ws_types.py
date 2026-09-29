"""Minimal structural types so services never import FastAPI directly."""

from __future__ import annotations

from typing import Protocol

from shared.events import Event


class WebSocketLike(Protocol):
    """Anything that can carry protocol frames (FastAPI WebSocket, test fakes)."""

    async def send_text(self, data: str) -> None: ...

    async def close(self, code: int = 1000) -> None: ...


class EventPublisher(Protocol):
    """Anything that can fan events out (Broadcaster, test fakes)."""

    async def publish_event(self, event: Event) -> None: ...
