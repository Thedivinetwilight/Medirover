"""MotionNode behavior against a fake backend over the in-memory link.

Covers: identification, heartbeat/telemetry emission, demo drive cycle,
e-stop override and recovery.
"""

from __future__ import annotations

import asyncio

import pytest

from firmware.common.node_context import NodeConfig
from firmware.communication.client import ClientSettings
from firmware.communication.simulated_transport import MemoryLink
from firmware.hardware.simulated import SimulatedHardware
from firmware.motion_node.node import MotionNode
from firmware.tests.fake_backend import FakeBackend
from shared.types import SafetyState

FAST = ClientSettings(
    heartbeat_interval_s=0.1,
    telemetry_interval_s=0.05,
    welcome_timeout_s=2.0,
    reconnect_backoff_initial_s=0.05,
    reconnect_backoff_max_s=0.2,
)


def _make_node(**overrides) -> tuple[MotionNode, FakeBackend, asyncio.Event, SimulatedHardware]:
    client_end, server_end = MemoryLink.pair()
    fake = FakeBackend(server_end)
    config = NodeConfig(
        node_id="motion-t",
        node_name="Test Motion Node",
        node_type="motion",
        capabilities=["demo-drive", "telemetry"],
        seed=7,
        heartbeat_interval_s=0.1,
        telemetry_interval_s=0.05,
        drive_every_s=0.3,
        drive_duration_s=0.2,
        **overrides,
    )
    hw = SimulatedHardware(config.node_id, seed=config.seed)
    node = MotionNode(config, hw, client_end, FAST)
    return node, fake, asyncio.Event(), hw


async def _wait_until(predicate, timeout_s: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("condition not met in time")


@pytest.mark.asyncio
async def test_identify_heartbeat_telemetry():
    node, fake, stop, hw = _make_node()
    tasks = [asyncio.create_task(node.run(stop)), asyncio.create_task(fake.run(stop))]
    try:
        await _wait_until(lambda: fake.identify is not None)
        assert fake.identify is not None
        assert fake.identify["node_id"] == "motion-t"
        assert fake.identify["node_type"] == "motion"
        assert fake.identify["source_kind"] == "SIMULATED"
        await _wait_until(lambda: len(fake.heartbeats) >= 3 and len(fake.telemetry) >= 2)
        hb = fake.heartbeats[-1]
        assert hb["safety_state"] in (SafetyState.READY.value, SafetyState.ACTIVE.value)
        assert hb["uptime_s"] >= 0
        assert hb["battery_voltage"] > 10.0
        sample_ids = {s["sensor_id"] for s in fake.telemetry[-1]["samples"]}
        assert {"battery_voltage", "encoder_left", "encoder_right", "motor_current"} <= sample_ids
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_drive_cycle_reaches_active_and_returns_to_ready():
    node, fake, stop, hw = _make_node()
    tasks = [asyncio.create_task(node.run(stop)), asyncio.create_task(fake.run(stop))]
    saw_active = asyncio.Event()

    def _watch() -> bool:
        if node.safety.state == SafetyState.ACTIVE:
            saw_active.set()
        return False

    try:
        await _wait_until(lambda: node.safety.state == SafetyState.READY)
        await _wait_until(lambda: node.safety.state == SafetyState.ACTIVE or saw_active.is_set())
        # encoders advanced while active
        assert hw.encoder_left > 0 or hw.encoder_right > 0
        await _wait_until(lambda: node.safety.state == SafetyState.READY, timeout_s=3.0)
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_estop_overrides_and_recovers():
    node, fake, stop, hw = _make_node()
    tasks = [asyncio.create_task(node.run(stop)), asyncio.create_task(fake.run(stop))]
    try:
        await _wait_until(lambda: node.safety.state == SafetyState.READY)
        hw.safety_input.engage()
        await _wait_until(lambda: node.safety.state == SafetyState.EMERGENCY_STOP, timeout_s=2.0)
        assert node.hw.motors.get_speeds() == (0.0, 0.0)
        # heartbeats must reflect EMERGENCY_STOP
        await _wait_until(
            lambda: (
                fake.heartbeats and fake.heartbeats[-1]["safety_state"] == SafetyState.EMERGENCY_STOP.value
            ),
            timeout_s=2.0,
        )
        hw.safety_input.release()
        await _wait_until(lambda: node.safety.state == SafetyState.READY, timeout_s=3.0)
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
