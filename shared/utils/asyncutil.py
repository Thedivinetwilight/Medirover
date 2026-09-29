"""Asyncio helpers shared across layers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine


def schedule(coro: Coroutine) -> None:
    """Schedule a coroutine on the running loop; no-op if there is none.

    Lets synchronous code trigger async work (e.g. broadcasts) without
    changing its signature. Errors inside the coroutine are logged by the
    loop's default handler and never propagate to the caller.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(coro)
