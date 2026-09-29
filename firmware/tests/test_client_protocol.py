"""Protocol client behavior: reconnect + re-identify, ping/ack roundtrip."""

from __future__ import annotations

import asyncio

import pytest

from firmware.common.node_context import NodeConfig
from firmware.communication.client import ClientSettings
from firmware.communication.simulated_transport import MemoryLink
from firmware.hardware.simulated import SimulatedHardware
from firmware.motion_node.node import MotionNode
from firmware.tests.fake_backend import FakeBackend


def _make() -> tuple[MotionNode, FakeBackend, asyncio.Event]:
    client_end, server_end = MemoryLink.pair()
    fake = FakeBackend(server_end)
    config = NodeConfig(
        node_id="motion-p",
        node_name="Proto Node",
        node_type="motion",
        seed=3,
        heartbeat_interval_s=0.1,
        telemetry_interval_s=0.05,
        drive_every_s=0,  # no driving in protocol tests
    )
    hw = SimulatedHardware(config.node_id, seed=config.seed)
    node = MotionNode(
        config,
        hw,
        client_end,
        ClientSettings(
            heartbeat_interval_s=0.1,
            telemetry_interval_s=0.05,
            welcome_timeout_s=2.0,
            reconnect_backoff_initial_s=0.05,
            reconnect_backoff_max_s=0.1,
        ),
    )
    return node, fake, asyncio.Event()


async def _wait_until(predicate, timeout_s: float = 5.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("condition not met in time")


@pytest.mark.asyncio
async def test_reconnect_and_reidentify():
    node, fake, stop = _make()
    tasks = [asyncio.create_task(node.run(stop)), asyncio.create_task(fake.run(stop))]
    try:
        await _wait_until(lambda: len(fake.heartbeats) >= 2)
        # server drops the link (simulates backend restart / network failure)
        await fake.end.close()
        await _wait_until(lambda: fake.identify_count >= 2, timeout_s=5.0)
        assert node.last_client is not None
        assert node.last_client.connection_count >= 2
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_ping_ack_roundtrip():
    node, fake, stop = _make()
    tasks = [asyncio.create_task(node.run(stop)), asyncio.create_task(fake.run(stop))]
    try:
        await _wait_until(lambda: len(fake.heartbeats) >= 1)
        ping_id = await fake.send_ping()
        await _wait_until(lambda: len(fake.acks) >= 1, timeout_s=3.0)
        payload, _acked_env_id = fake.acks[0]
        assert payload["message_id"] == ping_id
        assert payload["outcome"] == "ACCEPTED"
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
