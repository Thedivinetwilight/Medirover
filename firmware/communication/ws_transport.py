"""WebSocket transport for the node protocol client (real link)."""

from __future__ import annotations

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from firmware.hardware.interfaces import ICommunication


class WebSocketNodeTransport(ICommunication):
    def __init__(self, url: str, *, max_size: int = 64 * 1024, open_timeout: float = 5.0) -> None:
        self._url = url
        self._max_size = max_size
        self._open_timeout = open_timeout
        self._ws: ClientConnection | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(self) -> None:
        self._ws = await connect(self._url, max_size=self._max_size, open_timeout=self._open_timeout)

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    async def send(self, frame: str) -> None:
        if self._ws is None:
            raise ConnectionError("transport not connected")
        await self._ws.send(frame)

    async def recv(self) -> str | None:
        if self._ws is None:
            return None
        try:
            message = await self._ws.recv()
        except ConnectionClosed:
            self._ws = None
            return None
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return message
