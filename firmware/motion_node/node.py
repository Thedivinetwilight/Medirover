"""MotionNode: the first real (simulated) subsystem.

Behavior:
- initializes SAFE -> READY
- emits heartbeats (safety state, uptime, battery) and telemetry (sensors)
- runs a self-issued demo drive cycle: READY -> ACTIVE -> READY
  (v0.1: the node issues its own demo commands; operator-issued commands
   arrive with the M6/M7 command channel)
- watches the e-stop input with highest priority:
  engage -> EMERGENCY_STOP + motors stop; release -> RECOVERY -> READY
"""

from __future__ import annotations

import asyncio
import logging
import time

from firmware.common.node_context import NodeConfig
from firmware.communication.client import ClientSettings, NodeProtocolClient
from firmware.hardware.interfaces import ICommunication
from firmware.hardware.simulated import SimulatedHardware
from shared.safety import make_safety_fsm
from shared.types import SafetyEvent, SafetyState

HARDWARE_STEP_S = 0.05
ESTOP_SCAN_S = 0.05


class MotionNode:
    def __init__(
        self,
        config: NodeConfig,
        hardware: SimulatedHardware,
        transport: ICommunication,
        client_settings: ClientSettings | None = None,
    ) -> None:
        self.config = config
        self.hw = hardware
        self.transport = transport
        self.client_settings = client_settings
        self.safety = make_safety_fsm()
        self._started_at = time.monotonic()
        self._tick = 0
        self.log = logging.getLogger(f"medirover.node.{config.node_id}")
        self.last_client: NodeProtocolClient | None = None
        self.stop_event: asyncio.Event | None = None

    def stop(self) -> None:
        """Request a clean shutdown (idempotent)."""
        if self.stop_event is not None:
            self.stop_event.set()

    # -------------------------------------------------------------- payloads

    def heartbeat_payload(self) -> dict:
        return {
            "safety_state": self.safety.state.value,
            "uptime_s": round(time.monotonic() - self._started_at, 3),
            "battery_voltage": self.hw.battery_voltage(),
        }

    def telemetry_payload(self) -> dict:
        samples = []
        for sensor in self.hw.sensors():
            samples.append(
                {
                    "sensor_id": sensor.sensor_id,
                    "value": sensor.read(),
                    "unit": sensor.unit,
                    "quality": "ok" if sensor.healthy() else "degraded",
                }
            )
        self._tick += 1
        return {"tick": self._tick, "samples": samples}

    # ------------------------------------------------------------------- run

    async def run(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event
        self.safety.send(SafetyEvent.INIT_OK)  # SAFE -> READY
        self.log.info("initialized -> %s", self.safety.state.value)
        client = NodeProtocolClient(
            self.config,
            self.transport,
            self.client_settings,
            heartbeat_provider=self.heartbeat_payload,
            telemetry_provider=self.telemetry_payload,
        )
        self.last_client = client
        tasks = [
            asyncio.create_task(client.run(stop_event), name="client"),
            asyncio.create_task(self._hardware_loop(stop_event), name="hw"),
            asyncio.create_task(self._estop_watchdog(stop_event), name="estop"),
        ]
        if self.config.drive_every_s > 0:
            tasks.append(asyncio.create_task(self._drive_loop(stop_event), name="drive"))
        try:
            await asyncio.gather(*tasks)
        except Exception:  # noqa: BLE001
            self.log.exception("node task failed")
        finally:
            self.hw.motors.stop()
            self.log.info("node stopped (safety=%s)", self.safety.state.value)

    # ---------------------------------------------------------------- loops

    async def _hardware_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            self.hw.step(HARDWARE_STEP_S)
            await asyncio.sleep(HARDWARE_STEP_S)

    async def _estop_watchdog(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            engaged = self.hw.safety_input.e_stop_engaged()
            if engaged and self.safety.state != SafetyState.EMERGENCY_STOP:
                if self.safety.can(SafetyEvent.E_STOP):
                    self.safety.send(SafetyEvent.E_STOP)
                    self.hw.motors.stop()
                    self.hw.set_indicators({"e_stop": True})
                    self.log.critical("EMERGENCY STOP engaged")
            elif not engaged and self.safety.state == SafetyState.EMERGENCY_STOP:
                self.safety.send(SafetyEvent.E_STOP_RELEASED)  # -> RECOVERY
                self.hw.set_indicators({"e_stop": False})
                self.log.warning("e-stop released; running recovery checks")
                await asyncio.sleep(0.2)  # simulated diagnostics
                if self.safety.can(SafetyEvent.RECOVERY_OK):
                    self.safety.send(SafetyEvent.RECOVERY_OK)
                    self.log.info("recovery complete -> %s", self.safety.state.value)
            await asyncio.sleep(ESTOP_SCAN_S)

    async def _drive_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await asyncio.sleep(self.config.drive_every_s)
            if stop_event.is_set():
                return
            if self.safety.state != SafetyState.READY or not self.safety.can(SafetyEvent.COMMAND_ACCEPT):
                continue  # safety (e-stop/fault/recovery) takes precedence
            self.safety.send(SafetyEvent.COMMAND_ACCEPT)
            self.hw.motors.set_speed(self.config.drive_speed_mps, self.config.drive_speed_mps)
            self.log.info("demo drive accepted -> ACTIVE at %.2f m/s", self.config.drive_speed_mps)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.config.drive_duration_s)
            except TimeoutError:
                self.hw.motors.stop()
                if self.safety.state == SafetyState.ACTIVE and self.safety.can(SafetyEvent.COMMAND_COMPLETE):
                    self.safety.send(SafetyEvent.COMMAND_COMPLETE)
                    self.log.info("demo drive complete -> READY")
            # If e-stop/fault interrupted, state is handled by the watchdog.
