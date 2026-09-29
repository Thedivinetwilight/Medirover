"""In-memory duplex transport for firmware tests (master directive §10).

MemoryLink.pair() gives two ICommunication endpoints; frames sent on one
appear in the other's recv(). close() on one end makes the peer's recv()
return None (link down).
"""

from __future__ import annotations

import asyncio

from firmware.hardware.interfaces import ICommunication

_CLOSED = object()


class _MemoryEnd(ICommunication):
    def __init__(self, name: str, out_queue: asyncio.Queue, in_queue: asyncio.Queue) -> None:
        self._name = name
        self._out = out_queue
        self._in = in_queue
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        if self._connected:
            await self._out.put(_CLOSED)
            self._connected = False

    async def send(self, frame: str) -> None:
        if not self._connected:
            raise ConnectionError(f"{self._name}: send on closed link")
        await self._out.put(frame)

    async def recv(self) -> str | None:
        item = await self._in.get()
        if item is _CLOSED:
            self._connected = False
            return None
        return item


class MemoryLink:
    @classmethod
    def pair(cls) -> tuple[_MemoryEnd, _MemoryEnd]:
        a_to_b: asyncio.Queue = asyncio.Queue()
        b_to_a: asyncio.Queue = asyncio.Queue()
        a = _MemoryEnd("A", a_to_b, b_to_a)
        b = _MemoryEnd("B", b_to_a, a_to_b)
        return a, b
