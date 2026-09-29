"""Dual (L298-class) motor driver with explicit safety interlocks (M8).

Wiring model per wheel: PWM duty channel, direction line, enable line.
Speeds are converted to duty via ``v_max_mps`` (the maximum speed the
driver is configured to produce; an UNKNOWN real value must be configured
explicitly by the integrator, never assumed silently).

Interlock order for ``set_speed``:
1. E-stop latch engaged  -> REJECTED_E_STOP
2. Fault latched         -> REJECTED_FAULT
3. Not enabled           -> REJECTED_NOT_ENABLED
4. Otherwise             -> APPLIED (duty/direction/enable written)

``stop()`` (rule: zero-velocity stopping cannot be blocked by software)
bypasses every interlock: it always writes zero duty and disables the
outputs, and it never raises.

E-stop release semantics: the E-stop latch is cleared ONLY through
``set_estop_latched(False)``, which the facade invokes after a physical
``EstopLatch.hardware_reset()`` succeeded (input observed de-asserted).
``clear_fault()`` can NEVER clear the E-stop.
"""

from __future__ import annotations

from enum import StrEnum

from firmware.hardware.real.ports import Board


class MotorCommandResult(StrEnum):
    APPLIED = "APPLIED"
    REJECTED_E_STOP = "REJECTED_E_STOP"
    REJECTED_FAULT = "REJECTED_FAULT"
    REJECTED_NOT_ENABLED = "REJECTED_NOT_ENABLED"


class MotorFault(StrEnum):
    NONE = "NONE"
    OVERCURRENT = "OVERCURRENT"
    E_STOP = "E_STOP"
    MANUAL = "MANUAL"


class DualMotorDriver:
    def __init__(
        self,
        board: Board,
        *,
        left_pwm: int,
        left_dir: int,
        left_en: int,
        right_pwm: int,
        right_dir: int,
        right_en: int,
        v_max_mps: float = 1.0,
    ) -> None:
        if v_max_mps <= 0:
            raise ValueError("v_max_mps must be > 0 (do not guess the real maximum)")
        self._board = board
        self._ch = {
            "left": (left_pwm, left_dir, left_en),
            "right": (right_pwm, right_dir, right_en),
        }
        self._v_max = v_max_mps
        self._enabled = False
        self._fault: MotorFault = MotorFault.NONE
        self._estop_latched = False
        self.last_result: MotorCommandResult = MotorCommandResult.REJECTED_NOT_ENABLED
        self._apply_zero()

    # -- state -------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def fault(self) -> MotorFault:
        return self._fault

    @property
    def estop_latched(self) -> bool:
        return self._estop_latched

    def enable(self) -> None:
        """Explicit operator enable — no motion happens before this (rule 4)."""
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
        self._apply_zero()

    def set_estop_latched(self, engaged: bool) -> None:
        """Facade hook driven by the physical E-stop latch.

        Engage: zero outputs immediately and latch the E_STOP fault.
        Release (only legal after physical de-assertion): lift the latch
        and the E_STOP fault, and require a fresh explicit enable.
        """
        self._estop_latched = engaged
        if engaged:
            if self._fault is MotorFault.NONE:
                self._fault = MotorFault.E_STOP
            self._apply_zero()
        elif self._fault is MotorFault.E_STOP:
            self._fault = MotorFault.NONE
            self._enabled = False
            self._apply_zero()

    def trip(self, fault: MotorFault) -> None:
        """Latching fault: blocks commands until clear_fault()."""
        self._fault = fault
        self._apply_zero()

    def clear_fault(self) -> bool:
        """Operator action after the fault cause is resolved.

        Clears OVERCURRENT/MANUAL faults only — an E_STOP can never be
        cleared here (see set_estop_latched). Returns True when a fault
        was cleared; on any clear the driver requires re-enable.
        """
        if self._fault in (MotorFault.OVERCURRENT, MotorFault.MANUAL):
            self._fault = MotorFault.NONE
            self._enabled = False
            self._apply_zero()
            return True
        return False

    # -- commands ----------------------------------------------------------

    def set_speed(self, left_mps: float, right_mps: float) -> MotorCommandResult:
        if self._estop_latched:
            self.last_result = MotorCommandResult.REJECTED_E_STOP
        elif self._fault is not MotorFault.NONE:
            self.last_result = MotorCommandResult.REJECTED_FAULT
        elif not self._enabled:
            self.last_result = MotorCommandResult.REJECTED_NOT_ENABLED
        else:
            self._write(self._ch["left"], left_mps)
            self._write(self._ch["right"], right_mps)
            self.last_result = MotorCommandResult.APPLIED
        return self.last_result

    def stop(self) -> None:
        """Immediate zero-velocity command. Bypasses all interlocks, never raises."""
        try:
            self._apply_zero()
        except Exception:  # noqa: BLE001 — a stop must not be blocked even by a broken port
            pass

    # -- internals ---------------------------------------------------------

    def _write(self, side: tuple[int, int, int], mps: float) -> None:
        pwm, direction, enable = side
        if mps == 0.0:
            self._board.pwm_set_duty(pwm, 0.0)
            self._board.gpio_write(enable, False)
            return
        self._board.pwm_set_duty(pwm, max(0.0, min(1.0, abs(mps) / self._v_max)))
        self._board.gpio_write(direction, mps < 0.0)
        self._board.gpio_write(enable, True)

    def _apply_zero(self) -> None:
        for pwm, _direction, enable in self._ch.values():
            self._board.pwm_set_duty(pwm, 0.0)
            self._board.gpio_write(enable, False)
