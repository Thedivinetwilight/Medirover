"""SensorNode: telemetry-only node (battery + node health)."""

from __future__ import annotations

import asyncio
import logging
import time

from firmware.common.node_context import NodeConfig
from firmware.communication.client import ClientSettings, NodeProtocolClient
from firmware.hardware.interfaces import ICommunication, IHardware
from shared.safety import make_safety_fsm
from shared.types import SafetyEvent, SafetyState


class SensorNode:
    def __init__(
        self,
        config: NodeConfig,
        hardware: IHardware,
        transport: ICommunication,
        client_settings: ClientSettings | None = None,
    ) -> None:
        self.config = config.model_copy(update={"source_kind": hardware.source_kind})
        self.hw = hardware
        self.transport = transport
        self.client_settings = client_settings
        self.safety = make_safety_fsm()
        self._started_at = time.monotonic()
        self._tick = 0
        self.log = logging.getLogger(f"medirover.node.{config.node_id}")

    def heartbeat_payload(self) -> dict:
        return {
            "safety_state": self.safety.state.value,
            "uptime_s": round(time.monotonic() - self._started_at, 3),
            "battery_voltage": self.hw.battery_voltage(),
        }

    def telemetry_payload(self) -> dict:
        samples: list[dict] = []
        battery_v = self.hw.battery_voltage()
        if battery_v is not None:
            samples.append(
                {
                    "sensor_id": "battery_voltage",
                    "value": battery_v,
                    "unit": "V",
                    "quality": "ok" if self.hw.sensors()[0].healthy() else "degraded",
                }
            )
        samples.append(
            {
                "sensor_id": "node_health",
                "value": 1.0
                if self.safety.state not in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP)
                else 0.0,
                "unit": "ratio",
                "quality": "ok",
            }
        )
        self._tick += 1
        return {"tick": self._tick, "samples": samples}

    async def run(self, stop_event: asyncio.Event) -> None:
        self.safety.send(SafetyEvent.INIT_OK)
        client = NodeProtocolClient(
            self.config,
            self.transport,
            self.client_settings,
            heartbeat_provider=self.heartbeat_payload,
            telemetry_provider=self.telemetry_payload,
        )

        async def _estop_watchdog() -> None:
            while not stop_event.is_set():
                if self.hw.safety_input.e_stop_engaged() and self.safety.state != SafetyState.EMERGENCY_STOP:
                    if self.safety.can(SafetyEvent.E_STOP):
                        self.safety.send(SafetyEvent.E_STOP)
                        self.log.critical("EMERGENCY STOP engaged")
                elif (
                    not self.hw.safety_input.e_stop_engaged()
                    and self.safety.state == SafetyState.EMERGENCY_STOP
                ):
                    self.safety.send(SafetyEvent.E_STOP_RELEASED)
                    await asyncio.sleep(0.2)
                    if self.safety.can(SafetyEvent.RECOVERY_OK):
                        self.safety.send(SafetyEvent.RECOVERY_OK)
                await asyncio.sleep(0.05)

        tasks = [
            asyncio.create_task(client.run(stop_event), name="client"),
            asyncio.create_task(_estop_watchdog(), name="estop"),
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception:  # noqa: BLE001
            self.log.exception("sensor node task failed")
        self.log.info("sensor node stopped (safety=%s)", self.safety.state.value)
