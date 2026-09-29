"""Node connectivity state machine (backend's view of a node).

    DISCONNECTED --WS_CONNECTED--> CONNECTING
    CONNECTING   --IDENTIFY_OK-->  ONLINE
    CONNECTING   --IDENTIFY_FAILED/DISCONNECT--> DISCONNECTED
    ONLINE       --HEARTBEAT_LATE--> STALE
    ONLINE       --HEARTBEAT_TIMEOUT/WS_CLOSED--> OFFLINE
    STALE        --HEARTBEAT_OK--> ONLINE
    STALE        --HEARTBEAT_TIMEOUT/WS_CLOSED--> OFFLINE
    OFFLINE      --WS_CONNECTED--> CONNECTING
    DISCONNECTED --WS_CONNECTED--> CONNECTING

Notes:
- "WS_CONNECTED" is applied when an *identify* for a known node is received
  (a raw socket connect does not yet name the node).
- OFFLINE is sticky until a new connection + successful identify.
- If the safety state is EMERGENCY_STOP/FAULT the UI shows the safety chip
  on top of the connectivity chip; both axes are reported independently.
"""

from __future__ import annotations

from shared.fsm import StateMachine
from shared.types import ConnectivityEvent as E
from shared.types import ConnectivityState as S

CONNECTIVITY_STATES: set[S] = {
    S.DISCONNECTED,
    S.CONNECTING,
    S.ONLINE,
    S.STALE,
    S.OFFLINE,
}

CONNECTIVITY_TRANSITIONS: dict[tuple[S, E], S] = {
    (S.DISCONNECTED, E.WS_CONNECTED): S.CONNECTING,
    (S.OFFLINE, E.WS_CONNECTED): S.CONNECTING,
    (S.CONNECTING, E.IDENTIFY_OK): S.ONLINE,
    (S.CONNECTING, E.IDENTIFY_FAILED): S.DISCONNECTED,
    (S.CONNECTING, E.WS_CLOSED): S.DISCONNECTED,
    (S.ONLINE, E.HEARTBEAT_LATE): S.STALE,
    (S.ONLINE, E.HEARTBEAT_OK): S.ONLINE,  # explicit no-op transition (idempotent)
    (S.ONLINE, E.HEARTBEAT_TIMEOUT): S.OFFLINE,
    (S.ONLINE, E.WS_CLOSED): S.OFFLINE,
    (S.STALE, E.HEARTBEAT_OK): S.ONLINE,
    (S.STALE, E.HEARTBEAT_TIMEOUT): S.OFFLINE,
    (S.STALE, E.WS_CLOSED): S.OFFLINE,
}


def make_connectivity_fsm(initial: S = S.DISCONNECTED) -> StateMachine[S, E]:
    return StateMachine(
        name="connectivity",
        states=CONNECTIVITY_STATES,
        initial=initial,
        transitions=CONNECTIVITY_TRANSITIONS,
    )
