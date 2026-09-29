"""Exhaustive connectivity state machine tests (directive §13)."""

from __future__ import annotations

import pytest

from backend.state.node_fsm import (
    CONNECTIVITY_STATES,
    CONNECTIVITY_TRANSITIONS,
    make_connectivity_fsm,
)
from shared.fsm import FSMError
from shared.types import ConnectivityEvent as E
from shared.types import ConnectivityState as S

ALL_EVENTS = list(E)


@pytest.mark.parametrize("state", sorted(CONNECTIVITY_STATES, key=str))
@pytest.mark.parametrize("event", ALL_EVENTS)
def test_exhaustive_transitions(state: S, event: E):
    fsm = make_connectivity_fsm(initial=state)
    key = (state, event)
    if key in CONNECTIVITY_TRANSITIONS:
        assert fsm.send(event) == CONNECTIVITY_TRANSITIONS[key]
    else:
        with pytest.raises(FSMError):
            fsm.send(event)


def test_full_lifecycle():
    fsm = make_connectivity_fsm()
    assert fsm.send(E.WS_CONNECTED) == S.CONNECTING
    assert fsm.send(E.IDENTIFY_OK) == S.ONLINE
    assert fsm.send(E.HEARTBEAT_LATE) == S.STALE
    assert fsm.send(E.HEARTBEAT_OK) == S.ONLINE
    assert fsm.send(E.WS_CLOSED) == S.OFFLINE
    assert fsm.send(E.WS_CONNECTED) == S.CONNECTING
    assert fsm.send(E.IDENTIFY_OK) == S.ONLINE


def test_offline_is_sticky_until_reidentify():
    fsm = make_connectivity_fsm(initial=S.OFFLINE)
    # no heartbeat event is valid from OFFLINE
    with pytest.raises(FSMError):
        fsm.send(E.HEARTBEAT_OK)
