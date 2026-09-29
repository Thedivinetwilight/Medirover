"""Explicit state machine engine (master directive §13).

Every state machine in Medirover is a data-driven table:
states, initial state, and an explicit (state, event) -> state map.
Invalid transitions raise FSMError — they never silently no-op.
"""

from shared.fsm.base import FSMError, StateMachine

__all__ = ["FSMError", "StateMachine"]
