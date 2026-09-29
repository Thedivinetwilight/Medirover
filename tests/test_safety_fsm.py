"""Exhaustive safety state machine tests (directive §12, §13).

Every (state, event) pair is checked: either the exact expected next state,
or an explicit FSMError. No transition is allowed to silently no-op.
"""

from __future__ import annotations

import pytest

from shared.fsm import FSMError
from shared.safety import (
    SAFETY_STATES,
    SAFETY_TRANSITIONS,
    make_safety_fsm,
)
from shared.types import SafetyEvent as E
from shared.types import SafetyState as S

ALL_EVENTS = list(E)


def test_all_states_declared():
    assert SAFETY_STATES == {S.SAFE, S.READY, S.ACTIVE, S.WARNING, S.FAULT, S.EMERGENCY_STOP, S.RECOVERY}


@pytest.mark.parametrize("state", list(SAFETY_STATES))
@pytest.mark.parametrize("event", ALL_EVENTS)
def test_exhaustive_transitions(state: S, event: E):
    fsm = make_safety_fsm(initial=state)
    key = (state, event)
    if key in SAFETY_TRANSITIONS:
        assert fsm.send(event) == SAFETY_TRANSITIONS[key]
    else:
        with pytest.raises(FSMError):
            fsm.send(event)


@pytest.mark.parametrize("state", [s for s in SAFETY_STATES if s != S.EMERGENCY_STOP])
def test_estop_reachable_from_every_operational_state(state: S):
    fsm = make_safety_fsm(initial=state)
    assert fsm.can(E.E_STOP)
    assert fsm.send(E.E_STOP) == S.EMERGENCY_STOP


def test_estop_has_single_exit():
    fsm = make_safety_fsm(initial=S.EMERGENCY_STOP)
    allowed = fsm.allowed_events()
    assert allowed == [E.E_STOP_RELEASED]
    assert fsm.send(E.E_STOP_RELEASED) == S.RECOVERY


def test_recovery_success_and_failure_paths():
    fsm = make_safety_fsm(initial=S.RECOVERY)
    assert fsm.send(E.RECOVERY_OK) == S.READY

    fsm2 = make_safety_fsm(initial=S.RECOVERY)
    assert fsm2.send(E.RECOVERY_FAILED) == S.FAULT


def test_anomaly_while_active_is_a_fault():
    """Moving + anomaly must not degrade to a soft warning."""
    fsm = make_safety_fsm(initial=S.ACTIVE)
    assert fsm.send(E.ANOMALY) == S.FAULT


def test_invalid_transition_error_carries_context():
    fsm = make_safety_fsm(initial=S.EMERGENCY_STOP)
    with pytest.raises(FSMError) as exc_info:
        fsm.send(E.COMMAND_ACCEPT)
    err = exc_info.value
    assert err.code.code == "SAFETY_INVALID_TRANSITION"
    assert err.state == S.EMERGENCY_STOP
    assert err.recoverable is False


def test_e_stop_cannot_be_bypassed_by_commands():
    """A command acceptance must be impossible while e-stopped."""
    fsm = make_safety_fsm(initial=S.EMERGENCY_STOP)
    assert not fsm.can(E.COMMAND_ACCEPT)
