"""Safety state machine (master directive §12).

Safety is an independent subsystem that can override normal operation:
E_STOP is reachable from every operational state, and UI commands can
never bypass it (see docs/SAFETY.md for the full table).

STATUS: SIMULATION-VERIFIED only. No physical e-stop exists in this
repository (see docs/HARDWARE.md).
"""

from shared.safety.machine import (
    SAFETY_STATE_DESCRIPTIONS,
    SAFETY_STATES,
    SAFETY_TRANSITIONS,
    make_safety_fsm,
)

__all__ = [
    "SAFETY_STATES",
    "SAFETY_TRANSITIONS",
    "SAFETY_STATE_DESCRIPTIONS",
    "make_safety_fsm",
]
