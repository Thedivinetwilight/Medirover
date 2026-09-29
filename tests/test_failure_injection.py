"""Failure injection over the real node WebSocket (directive §20).

Injected failures: malformed frames, unknown type, version mismatch,
duplicate, out-of-order, stale, sensor degradation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from shared.protocols.codec import encode_frame
from shared.schemas.envelope import Envelope
from shared.utils.ids import new_message_id
from shared.utils.timeutil import now_utc

pytestmark = pytest.mark.e2e


def _frame(
    message_type: str,
    node_id: str = "motion-fi",
    sequence: int = 0,
    message_id: str | None = None,
    payload: dict | None = None,
    protocol_version: int = 1,
    ts=None,
) -> str:
    return encode_frame(
        Envelope(
            protocol_version=protocol_version,
            message_version=1,
            message_type=message_type,
            message_id=message_id or new_message_id(),
            sequence=sequence,
            timestamp=ts or now_utc(),
            node_id=node_id,
            payload=payload if payload is not None else {},
        )
    )


IDENTIFY_PAYLOAD = {
    "node_id": "motion-fi",
    "node_name": "FI Node",
    "node_type": "motion",
    "firmware_version": "0.1.0",
    "capabilities": [],
}


async def _connect(url: str):
    return await connect(url)


async def _first_reject(ws) -> dict:
    while True:
        raw = await ws.recv()
        frame = json.loads(raw)
        if frame["message_type"] == "reject":
            return frame
        # welcome frames are fine to skip


async def test_malformed_frames_close_connection(server):
    ws = await _connect(f"ws://127.0.0.1:{server.port}/ws/node")
    rejects = 0
    closed = False
    try:
        for _ in range(3):
            await ws.send("this is not json")
            try:
                while True:
                    frame = json.loads(await ws.recv())
                    if frame["message_type"] == "reject":
                        rejects += 1
            except ConnectionClosed:
                closed = True
                break
        if not closed:
            # drain any remaining frames until the close arrives
            try:
                while True:
                    await ws.recv()
            except ConnectionClosed:
                closed = True
    finally:
        await ws.close()
    assert rejects >= 2
    assert closed


async def test_unknown_message_type_rejected(server):
    ws = await _connect(f"ws://127.0.0.1:{server.port}/ws/node")
    try:
        await ws.send(_frame("explosion", payload={"boom": True}))
        reject = await _first_reject(ws)
        assert reject["payload"]["error_code"] == "PROTOCOL_UNKNOWN_TYPE"
    finally:
        await ws.close()


async def test_protocol_version_mismatch_rejected(server):
    ws = await _connect(f"ws://127.0.0.1:{server.port}/ws/node")
    try:
        await ws.send(_frame("identify", payload=IDENTIFY_PAYLOAD, protocol_version=99))
        reject = await _first_reject(ws)
        assert reject["payload"]["error_code"] == "PROTOCOL_VERSION_MISMATCH"
    finally:
        await ws.close()


async def test_stale_frame_rejected(server):
    ws = await _connect(f"ws://127.0.0.1:{server.port}/ws/node")
    try:
        old_ts = now_utc() - timedelta(seconds=120)
        await ws.send(_frame("identify", payload=IDENTIFY_PAYLOAD, ts=old_ts))
        reject = await _first_reject(ws)
        assert reject["payload"]["error_code"] == "PROTOCOL_STALE"
    finally:
        await ws.close()


async def test_duplicate_and_out_of_order_rejected(server):
    ws = await _connect(f"ws://127.0.0.1:{server.port}/ws/node")
    try:
        # identify (seq 0) -> welcome
        await ws.send(_frame("identify", payload=IDENTIFY_PAYLOAD, sequence=0))
        welcome = json.loads(await ws.recv())
        assert welcome["message_type"] == "welcome"

        hb1 = _frame(
            "heartbeat",
            sequence=1,
            payload={"safety_state": "READY", "uptime_s": 1.0, "battery_voltage": 12.5},
        )
        await ws.send(hb1)
        await asyncio.sleep(0.2)  # let the server process it

        # duplicate (same message_id)
        await ws.send(hb1)
        reject = await _first_reject(ws)
        assert reject["payload"]["error_code"] == "PROTOCOL_DUPLICATE"

        # out of order (new id, seq <= last)
        await ws.send(_frame("heartbeat", sequence=1, payload={"safety_state": "READY", "uptime_s": 1.1}))
        reject = await _first_reject(ws)
        assert reject["payload"]["error_code"] == "PROTOCOL_OUT_OF_ORDER"
    finally:
        await ws.close()


async def test_sensor_degraded_event(node, api_client):
    """A degraded sensor sample must produce a bounded WARNING event."""
    from tests.conftest import wait_until

    node.hw.mark_degraded("battery_voltage", True)

    async def has_degraded_event():
        resp = await api_client.get("/api/v1/events", params={"limit": 100})
        return any(e["event_type"] == "SENSOR_DEGRADED" and e["severity"] == "WARNING" for e in resp.json())

    await wait_until(has_degraded_event, timeout_s=8.0)
    node.hw.mark_degraded("battery_voltage", False)
