"""WebSocket endpoint for node connections (firmware side).

Thin transport handler — all protocol/state logic lives in NodeManager.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.deps import get_ctx

router = APIRouter()
logger = logging.getLogger("medirover.ws.node")


@router.websocket("/ws/node")
async def node_ws(ws: WebSocket) -> None:
    ctx = get_ctx(ws)
    await ws.accept()
    conn = ctx.node_manager.register_connection(ws)
    if conn is None:
        await ws.close(code=1013)  # try again later
        return
    try:
        while True:
            raw = await ws.receive_text()
            frames, close = await ctx.node_manager.handle(conn.conn_id, raw)
            for frame in frames:
                await ws.send_text(frame)
            if close:
                await ws.close(code=1008)
                return
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never let one connection kill the handler loop
        logger.exception("node websocket error", extra={"conn_id": conn.conn_id})
        try:
            await ws.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
    finally:
        ctx.node_manager.on_disconnect(conn.conn_id)
