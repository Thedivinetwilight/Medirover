"""Board-level I/O ports — the physical boundary for real drivers (M8).

Real drivers (motors, E-stop, encoders, battery) are written against this
channel-based abstraction. A board implementation either drives actual
GPIO/PWM/ADC/counter hardware (M9/M10) or is the deterministic in-memory
`MemoryBoard` used for fault-injection tests at this boundary.

Nothing above this layer talks to a specific board model; nothing below it
knows about rover semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Board(ABC):
    """Channel-based board I/O. Channels are integer indices (wiring map)."""

    @abstractmethod
    def pwm_set_duty(self, channel: int, duty: float) -> None:
        """Set PWM duty in [0.0, 1.0]."""

    @abstractmethod
    def pwm_read_duty(self, channel: int) -> float:
        """Read back the last duty actually applied (verification aid)."""

    @abstractmethod
    def gpio_write(self, channel: int, on: bool) -> None: ...

    @abstractmethod
    def gpio_read(self, channel: int) -> bool:
        """Read a digital output or (for inputs) the physical line."""

    @abstractmethod
    def adc_read_mv(self, channel: int) -> int | None:
        """Analog read in millivolts, or None when no reading is available.

        None must never be replaced with a guessed value upstream.
        """

    @abstractmethod
    def counter_read(self, channel: int) -> int:
        """Monotonic counter value (e.g. encoder ticks)."""

    @abstractmethod
    def counter_reset(self, channel: int) -> None: ...


class MemoryBoard(Board):
    """Deterministic in-memory board — the test double at the physical boundary.

    Inputs (adc, counters, e-stop lines) are set explicitly by tests; outputs
    (pwm, gpio) are recorded for assertion. No randomness, no timing.
    """

    def __init__(self) -> None:
        self._pwm: dict[int, float] = {}
        self._gpio: dict[int, bool] = {}
        self._adc: dict[int, int | None] = {}
        self._counters: dict[int, int] = {}

    # -- outputs (recorded) ------------------------------------------------

    def pwm_set_duty(self, channel: int, duty: float) -> None:
        if not 0.0 <= duty <= 1.0:
            raise ValueError(f"duty out of range: {duty}")
        self._pwm[channel] = duty

    def pwm_read_duty(self, channel: int) -> float:
        return self._pwm.get(channel, 0.0)

    def gpio_write(self, channel: int, on: bool) -> None:
        self._gpio[channel] = bool(on)

    def gpio_read(self, channel: int) -> bool:
        return self._gpio.get(channel, False)

    # -- inputs (set by tests / driven by real hardware) -------------------

    def set_adc_mv(self, channel: int, mv: int | None) -> None:
        self._adc[channel] = mv

    def adc_read_mv(self, channel: int) -> int | None:
        return self._adc.get(channel)

    def set_counter(self, channel: int, value: int) -> None:
        self._counters[channel] = int(value)

    def counter_read(self, channel: int) -> int:
        return self._counters.get(channel, 0)

    def counter_reset(self, channel: int) -> None:
        self._counters[channel] = 0

    def set_input(self, channel: int, on: bool) -> None:
        """Set a physical input line (e-stop etc.) as seen by gpio_read."""
        self._gpio[channel] = bool(on)
