"""Latching emergency-stop input (M8).

Safety rules enforced here (audit items, recovery/SAFETY_AUDIT.md):
- Engage is immediate and latching: once the physical input asserts, the
  latch holds even if the input line momentarily de-asserts.
- Software can NEVER clear the latch alone. `hardware_reset()` only clears
  it when the physical input is observed de-asserted; if the input is still
  asserted, the latch re-engages immediately.
"""

from __future__ import annotations

from firmware.hardware.real.ports import Board


class EstopLatch:
    def __init__(self, board: Board, channel: int) -> None:
        self._board = board
        self._channel = channel
        self._engaged = False

    def poll(self) -> bool:
        """Refresh from the physical input. Returns current latch state."""
        if self._board.gpio_read(self._channel):
            self._engaged = True
        return self._engaged

    @property
    def engaged(self) -> bool:
        return self._engaged

    def hardware_reset(self) -> bool:
        """Operator-initiated latch clear.

        Returns True when the latch was cleared. If the physical input is
        still asserted, the latch re-engages and False is returned — a
        software-side call can never leave the system believing the E-stop
        is released while the input says otherwise.
        """
        self._engaged = False
        if self._board.gpio_read(self._channel):
            self._engaged = True
            return False
        return True
