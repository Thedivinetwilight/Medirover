"""First major vertical-slice acceptance test (directive §34).

    SIMULATED NODE -> IDENTIFY -> HEARTBEAT -> TELEMETRY -> BACKEND
    -> DATABASE -> API -> FRONTEND (WS) -> LIVE STATUS

Real uvicorn + real WebSockets + real SQLite. Deterministic (fixed seeds).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.conftest import wait_until

pytestmark = pytest.mark.e2e


async def _get_nodes(api_client):
    resp = await api_client.get("/api/v1/nodes")
    return resp.json()


async def test_vertical_slice_live_status(api_client, node, server):
    node_id = "motion-e2e"

    # 1+2: node identified, ONLINE, heartbeating
    async def is_online():
        nodes = await _get_nodes(api_client)
        return any(n["node_id"] == node_id and n["state"]["connectivity"] == "ONLINE" for n in nodes)

    await wait_until(is_online, timeout_s=10.0)

    # 3: telemetry flowing into the database
    async def telemetry_growing():
        resp = await api_client.get(f"/api/v1/nodes/{node_id}/telemetry", params={"limit": 5})
        return len(resp.json()) >= 2

    await wait_until(telemetry_growing, timeout_s=10.0)
    rows = (await api_client.get(f"/api/v1/nodes/{node_id}/telemetry", params={"limit": 5})).json()
    assert all(r["node_id"] == node_id for r in rows)
    sensor_ids = {r["sensor_id"] for r in rows}
    assert "battery_voltage" in sensor_ids

    # 3b: startup self-check complete (SAFE -> READY)
    async def is_ready():
        nodes = await _get_nodes(api_client)
        return any(n["node_id"] == node_id and n["state"]["safety_state"] == "READY" for n in nodes)

    await wait_until(is_ready, timeout_s=10.0)

    # 4: frontend WebSocket gets snapshot + live updates
    from websockets.asyncio.client import connect

    frames: list[dict] = []

    async def read_frames():
        async with connect(f"ws://127.0.0.1:{server.port}/ws/state") as ws:
            for _ in range(6):
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                frames.append(json.loads(raw))

    reader = asyncio.create_task(read_frames())
    await reader

    types = [f["message_type"] for f in frames]
    assert "state_snapshot" in types
    snapshot = next(f for f in frames if f["message_type"] == "state_snapshot")
    snap_nodes = {n["node_id"]: n for n in snapshot["payload"]["nodes"]}
    assert node_id in snap_nodes
    assert snap_nodes[node_id]["connectivity"] == "ONLINE"
    assert snap_nodes[node_id]["safety_state"] == "READY"
    assert "state_update" in types or "event" in types  # live feed is moving

    # 5: events recorded (identify + ongoing)
    events = (await api_client.get("/api/v1/events", params={"limit": 100})).json()
    event_types = {e["event_type"] for e in events}
    assert "NODE_IDENTIFIED" in event_types
    assert all(e["node_id"] == node_id or e["node_id"] is None for e in events)

    # 6: node registry persisted in DB
    detail = (await api_client.get(f"/api/v1/nodes/{node_id}")).json()
    assert detail["node"]["name"] == "E2E Node motion-e2e"
    assert detail["node"]["node_type"] == "motion"
    assert detail["node"]["capabilities"] == ["demo-drive", "telemetry"]
