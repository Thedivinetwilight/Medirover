"""Battery monitoring with explicit UNKNOWN (M8).

Rule: unknown hardware / missing readings are never guessed. When the ADC
has no reading, `voltage()` returns None and `state()` is UNKNOWN — the
sensor is reported degraded, never a fabricated number.
"""

from __future__ import annotations

from enum import StrEnum

from firmware.hardware.real.ports import Board


class BatteryState(StrEnum):
    OK = "OK"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class BatteryMonitor:
    def __init__(
        self,
        board: Board,
        channel: int,
        *,
        low_v: float,
        critical_v: float,
        mv_per_v: int = 1,
    ) -> None:
        if not (critical_v < low_v):
            raise ValueError("thresholds must satisfy critical_v < low_v")
        self._board = board
        self._channel = channel
        self._low_v = low_v
        self._critical_v = critical_v
        self._mv_per_v = mv_per_v

    def voltage(self) -> float | None:
        mv = self._board.adc_read_mv(self._channel)
        if mv is None:
            return None  # no reading — never guess
        return (mv / self._mv_per_v) / 1000.0

    def state(self) -> BatteryState:
        v = self.voltage()
        if v is None:
            return BatteryState.UNKNOWN
        if v < self._critical_v:
            return BatteryState.CRITICAL
        if v < self._low_v:
            return BatteryState.LOW
        return BatteryState.OK
