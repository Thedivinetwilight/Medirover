"""Simulated hardware (master directive §10).

Deterministic given a seed. Models the minimum physics the node logic
needs: battery drain, motor speed response, encoder integration, and an
e-stop input that scenarios can engage/release.

STATUS: SIMULATION-VERIFIED. This is not a physical model of any real
rover; parameters are placeholders (real-hardware assumptions are UNKNOWN;
see docs/SAFETY.md and docs/STATUS_MATRIX.md).
"""

from __future__ import annotations

import random

from firmware.hardware.interfaces import (
    IHardware,
    IMotorController,
    IPowerMonitor,
    ISafetyInput,
    ISensor,
    IStatusOutput,
)
from shared.types import SourceKind

WHEEL_RADIUS_M = 0.05  # placeholder assumption (UNKNOWN real hardware)
SPEED_RAMP_MPS2 = 1.0  # simulated motor acceleration limit


class _SimSafetyInput(ISafetyInput):
    def __init__(self) -> None:
        self._engaged = False

    def e_stop_engaged(self) -> bool:
        return self._engaged

    def engage(self) -> None:
        self._engaged = True

    def release(self) -> None:
        self._engaged = False


class _SimStatus(IStatusOutput):
    def __init__(self) -> None:
        self.indicators: dict[str, bool] = {}

    def set_indicators(self, indicators: dict[str, bool]) -> None:
        self.indicators = dict(indicators)


class SimulatedSensor(ISensor):
    def __init__(
        self,
        sensor_id: str,
        unit: str,
        getter,
        health_check=None,
    ) -> None:
        self._id = sensor_id
        self._unit = unit
        self._getter = getter
        self._health = health_check or (lambda: True)

    @property
    def sensor_id(self) -> str:
        return self._id

    @property
    def unit(self) -> str:
        return self._unit

    def read(self) -> float:
        return float(self._getter())

    def healthy(self) -> bool:
        return bool(self._health())


class _SimMotors(IMotorController):
    def __init__(self, hw: SimulatedHardware) -> None:
        self._hw = hw

    def set_speed(self, left_mps: float, right_mps: float) -> None:
        self._hw._target_l = max(-1.0, min(1.0, left_mps))
        self._hw._target_r = max(-1.0, min(1.0, right_mps))

    def get_speeds(self) -> tuple[float, float]:
        return self._hw._speed_l, self._hw._speed_r

    def stop(self) -> None:
        self._hw._target_l = 0.0
        self._hw._target_r = 0.0


class _SimPower(IPowerMonitor):
    def __init__(self, hw: SimulatedHardware) -> None:
        self._hw = hw

    def battery_voltage(self) -> float | None:
        return self._hw.battery_voltage()

    def current_draw(self) -> float:
        return self._hw.motor_current()


class SimulatedHardware(IHardware):
    """The simulated physical world for one node (deterministic per seed)."""

    # Refine the interface types so test code can use simulation controls
    # (engage/release) without casts.
    safety_input: _SimSafetyInput
    motors: _SimMotors

    def __init__(self, node_id: str, seed: int = 42, initial_battery_v: float = 12.6) -> None:
        self.node_id = node_id
        self.seed = seed
        self.rng = random.Random(seed)
        self.battery_v = initial_battery_v
        self._target_l = 0.0
        self._target_r = 0.0
        self._speed_l = 0.0
        self._speed_r = 0.0
        self.encoder_left = 0
        self.encoder_right = 0
        self.safety_input = _SimSafetyInput()
        self.status = _SimStatus()
        self.motors = _SimMotors(self)
        self.power = _SimPower(self)
        self._degraded: set[str] = set()
        self._sensors: list[SimulatedSensor] = [
            SimulatedSensor(
                "battery_voltage", "V", self.battery_voltage, lambda: "battery_voltage" not in self._degraded
            ),
            SimulatedSensor("encoder_left", "ticks", lambda: float(self.encoder_left)),
            SimulatedSensor("encoder_right", "ticks", lambda: float(self.encoder_right)),
            SimulatedSensor(
                "motor_current", "A", self.motor_current, lambda: "motor_current" not in self._degraded
            ),
        ]

    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.SIMULATED

    # -- physics ----------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance simulated physics by dt seconds."""
        self._speed_l = self._approach(self._speed_l, self._target_l, SPEED_RAMP_MPS2 * dt)
        self._speed_r = self._approach(self._speed_r, self._target_r, SPEED_RAMP_MPS2 * dt)
        self.encoder_left += int(round(self._speed_l * dt / WHEEL_RADIUS_M * 1000))
        self.encoder_right += int(round(self._speed_r * dt / WHEEL_RADIUS_M * 1000))
        # Battery: 12.6V nominal, slow drain, small noise
        self.battery_v = max(
            9.0,
            self.battery_v
            - (0.0004 + 0.002 * (abs(self._speed_l) + abs(self._speed_r))) * dt
            + self.rng.uniform(-0.001, 0.001),
        )

    @staticmethod
    def _approach(current: float, target: float, max_delta: float) -> float:
        if current < target:
            return min(target, current + max_delta)
        if current > target:
            return max(target, current - max_delta)
        return current

    def motor_current(self) -> float:
        base = 0.05
        load = 0.8 * (abs(self._speed_l) + abs(self._speed_r))
        return base + load + self.rng.uniform(0.0, 0.02)

    def battery_voltage(self) -> float | None:
        return self.battery_v

    # -- sensors ----------------------------------------------------------

    def sensors(self) -> list[ISensor]:
        return list(self._sensors)

    def mark_degraded(self, sensor_id: str, degraded: bool) -> None:
        if degraded:
            self._degraded.add(sensor_id)
        else:
            self._degraded.discard(sensor_id)

    def set_indicators(self, indicators: dict[str, bool]) -> None:
        self.status.set_indicators(indicators)
