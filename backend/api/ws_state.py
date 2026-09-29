"""WebSocket endpoint for frontend dashboards.

Server -> client: state_snapshot, state_update, event, pong
Client -> server: subscribe {node_ids}, ping
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.deps import get_ctx
from shared.protocols.validator import FrameValidator
from shared.schemas.node import SubscribePayload
from shared.types import MessageDirection

router = APIRouter()
logger = logging.getLogger("medirover.ws.state")

CLIENT_BAD_FRAME_LIMIT = 5


@router.websocket("/ws/state")
async def state_ws(ws: WebSocket) -> None:
    ctx = get_ctx(ws)
    await ws.accept()
    validator = FrameValidator(MessageDirection.CLIENT_TO_BACKEND)
    ctx.broadcaster.register(ws)

    try:
        # Initial snapshot: all nodes + recent events
        await ctx.broadcaster.send_snapshot(
            ws,
            ctx.node_manager.node_states(),
            ctx.eventing.recent_events(limit=50),
        )
        while True:
            raw = await ws.receive_text()
            result = validator.validate(raw)
            if not result.is_valid:
                bad = ctx.broadcaster.mark_bad_frame(ws)
                logger.debug("bad client frame: %s (%s)", result.outcome.value, result.error_message)
                if bad >= CLIENT_BAD_FRAME_LIMIT:
                    await ws.close(code=1008)
                    return
                continue
            env = result.envelope
            assert env is not None
            if env.message_type == "subscribe":
                sub = SubscribePayload.model_validate(env.payload)
                ctx.broadcaster.set_filter(ws, set(sub.node_ids))
                logger.info("client subscribed to %s", sub.node_ids or "all nodes")
            elif env.message_type == "ping":
                await ctx.broadcaster.send_pong(ws)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("state websocket error")
    finally:
        ctx.broadcaster.unregister(ws)
