"""Encoder pair: velocity estimation, zero-velocity verification, stall
detection (M8).

Zero-velocity verification is the software-side companion to the rule that
a commanded stop must actually stop the mechanism: after `stop()`, the
node can confirm the encoders no longer advance.
"""

from __future__ import annotations

from firmware.hardware.real.ports import Board


class EncoderPair:
    def __init__(
        self,
        board: Board,
        left_channel: int,
        right_channel: int,
        ticks_per_meter: float,
    ) -> None:
        if ticks_per_meter <= 0:
            raise ValueError("ticks_per_meter must be > 0 (unknown hardware must not be guessed)")
        self._board = board
        self._left = left_channel
        self._right = right_channel
        self._ticks_per_m = ticks_per_meter
        self._last: tuple[int, int] | None = None

    def prime(self) -> None:
        """Take the baseline reading (call before the first velocity sample)."""
        self._last = (self._board.counter_read(self._left), self._board.counter_read(self._right))

    def raw(self) -> tuple[int, int]:
        return (self._board.counter_read(self._left), self._board.counter_read(self._right))

    def velocity(self, dt: float) -> tuple[float, float]:
        """Current speeds in m/s (signed, + = forward)."""
        if dt <= 0:
            raise ValueError("dt must be > 0")
        left, right = self.raw()
        if self._last is None:
            self._last = (left, right)
            return (0.0, 0.0)
        v_l = (left - self._last[0]) / self._ticks_per_m / dt
        v_r = (right - self._last[1]) / self._ticks_per_m / dt
        self._last = (left, right)
        return (v_l, v_r)

    def zero_velocity(self, dt: float, tolerance_mps: float = 0.01) -> bool:
        """True when neither wheel moved beyond tolerance during dt."""
        v_l, v_r = self.velocity(dt)
        return abs(v_l) <= tolerance_mps and abs(v_r) <= tolerance_mps

    def stalled(
        self,
        commanded_mps: tuple[float, float],
        dt: float,
        min_mps: float = 0.05,
    ) -> tuple[bool, bool]:
        """Per-wheel: commanded motion above min_mps but no encoder motion."""
        v_l, v_r = self.velocity(dt)
        l_stall = abs(commanded_mps[0]) >= min_mps and abs(v_l) < min_mps
        r_stall = abs(commanded_mps[1]) >= min_mps and abs(v_r) < min_mps
        return (l_stall, r_stall)
