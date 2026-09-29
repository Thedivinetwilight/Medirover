"""Disconnect / reconnect acceptance behavior (directive §34, §37).

Node disconnects -> system identifies OFFLINE -> event recorded -> UI state
shows OFFLINE -> reconnect -> state recovers. No duplicate node rows.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.conftest import wait_until

pytestmark = pytest.mark.e2e


async def _wait_online(api_client, node_id, timeout_s: float = 10.0):
    async def _check():
        resp = await api_client.get("/api/v1/nodes")
        nodes = resp.json()
        return any(n["node_id"] == node_id and n["state"]["connectivity"] == "ONLINE" for n in nodes)

    await wait_until(_check, timeout_s=timeout_s)


async def test_disconnect_marks_offline_and_reconnect_recovers(api_client, server, node_factory):
    node_id = "motion-dr"

    # attach a frontend WS listener first
    from websockets.asyncio.client import connect

    seen_updates: list[dict] = []

    async def listen():
        async with connect(f"ws://127.0.0.1:{server.port}/ws/state") as ws:
            for _ in range(40):
                raw = await asyncio.wait_for(ws.recv(), timeout=8.0)
                frame = json.loads(raw)
                if frame["message_type"] == "state_update" and frame["node_id"] == node_id:
                    seen_updates.append(frame["payload"])

    listener = asyncio.create_task(listen())

    # 1. first node goes online
    node = node_factory(node_id=node_id)
    stop = asyncio.Event()
    task = asyncio.create_task(node.run(stop))
    await _wait_online(api_client, node_id)

    # 2. clean disconnect
    node.stop()
    await task

    async def is_offline():
        resp = await api_client.get("/api/v1/nodes")
        nodes = {n["node_id"]: n for n in resp.json()}
        return nodes.get(node_id, {}).get("state", {}).get("connectivity") == "OFFLINE"

    await wait_until(is_offline, timeout_s=8.0)

    # 3. event recorded
    events = (await api_client.get("/api/v1/events", params={"limit": 100})).json()
    types = {e["event_type"] for e in events if e["node_id"] == node_id}
    assert "NODE_DISCONNECTED" in types or "NODE_OFFLINE" in types

    # 4. UI state feed saw the OFFLINE transition
    async def saw_offline():
        return any(u["connectivity"] == "OFFLINE" for u in seen_updates)

    await wait_until(saw_offline, timeout_s=8.0)

    # 5. reconnect with the same identity -> recovers ONLINE
    node2 = node_factory(node_id=node_id)
    stop2 = asyncio.Event()
    task2 = asyncio.create_task(node2.run(stop2))
    try:
        await _wait_online(api_client, node_id)

        # 6. exactly one node row for this identity (no duplication)
        resp = await api_client.get("/api/v1/nodes")
        matches = [n for n in resp.json() if n["node_id"] == node_id]
        assert len(matches) == 1
        assert matches[0]["state"]["connectivity"] == "ONLINE"

        # 7. telemetry continues after recovery
        async def telemetry_growing():
            r = await api_client.get(f"/api/v1/nodes/{node_id}/telemetry", params={"limit": 5})
            return len(r.json()) >= 2

        await wait_until(telemetry_growing, timeout_s=10.0)

        # 8. second identification recorded
        events2 = (await api_client.get("/api/v1/events", params={"limit": 100})).json()
        identified = [e for e in events2 if e["event_type"] == "NODE_IDENTIFIED" and e["node_id"] == node_id]
        assert len(identified) == 2
    finally:
        node2.stop()
        await task2
        listener.cancel()
