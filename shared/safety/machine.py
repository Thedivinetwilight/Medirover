"""The canonical safety state machine definition.

States
------
SAFE            powered on, not yet initialized, no motion possible
READY           initialized, waiting for commands, no motion
ACTIVE          executing a command (motion permitted by safety)
WARNING         non-critical anomaly detected; motion stopped, awaiting operator
FAULT           critical fault; motion halted; explicit recovery required
EMERGENCY_STOP  e-stop engaged (or forced); highest priority, overrides everything
RECOVERY        post-fault / post-e-stop diagnostics and restoration

Deterministic behaviors (see docs/SAFETY.md):
- communication loss   -> backend marks node OFFLINE; safety state frozen last-known
- stale command        -> rejected by protocol layer, no state change
- sensor failure       -> ANOMALY (WARNING) or FAULT per sensor criticality
- invalid command      -> SAFETY_CONSTRAINT / protocol rejection, no state change
- firmware failure     -> watchdog / supervisor marks node OFFLINE
- watchdog event       -> node reboots into SAFE (fresh initialization)
"""

from __future__ import annotations

from shared.fsm import StateMachine
from shared.types import SafetyEvent as E
from shared.types import SafetyState as S

SAFETY_STATES: set[S] = {
    S.SAFE,
    S.READY,
    S.ACTIVE,
    S.WARNING,
    S.FAULT,
    S.EMERGENCY_STOP,
    S.RECOVERY,
}

SAFETY_TRANSITIONS: dict[tuple[S, E], S] = {
    # Initialization
    (S.SAFE, E.INIT_OK): S.READY,
    # Normal operation
    (S.READY, E.COMMAND_ACCEPT): S.ACTIVE,
    (S.ACTIVE, E.COMMAND_COMPLETE): S.READY,
    # Anomalies
    (S.READY, E.ANOMALY): S.WARNING,
    (S.ACTIVE, E.ANOMALY): S.FAULT,  # anomaly while moving => halt + fault
    (S.WARNING, E.ANOMALY_CLEAR): S.READY,
    (S.WARNING, E.FAULT): S.FAULT,
    # Faults
    (S.READY, E.FAULT): S.FAULT,
    (S.FAULT, E.CLEAR_REQUESTED): S.RECOVERY,
    (S.RECOVERY, E.RECOVERY_OK): S.READY,
    (S.RECOVERY, E.RECOVERY_FAILED): S.FAULT,
    # Emergency stop — reachable from every state, single defined exit
    (S.SAFE, E.E_STOP): S.EMERGENCY_STOP,
    (S.READY, E.E_STOP): S.EMERGENCY_STOP,
    (S.ACTIVE, E.E_STOP): S.EMERGENCY_STOP,
    (S.WARNING, E.E_STOP): S.EMERGENCY_STOP,
    (S.FAULT, E.E_STOP): S.EMERGENCY_STOP,
    (S.RECOVERY, E.E_STOP): S.EMERGENCY_STOP,
    (S.EMERGENCY_STOP, E.E_STOP_RELEASED): S.RECOVERY,
}

SAFETY_STATE_DESCRIPTIONS: dict[S, str] = {
    S.SAFE: "Powered on, not initialized. No motion possible.",
    S.READY: "Initialized and idle. Accepts commands.",
    S.ACTIVE: "Executing a command. Motion permitted.",
    S.WARNING: "Non-critical anomaly; motion stopped; operator action expected.",
    S.FAULT: "Critical fault; motion halted; explicit recovery required.",
    S.EMERGENCY_STOP: "Emergency stop engaged. Overrides all commands.",
    S.RECOVERY: "Running post-fault/post-e-stop restoration checks.",
}


def make_safety_fsm(initial: S = S.SAFE) -> StateMachine[S, E]:
    return StateMachine(
        name="safety",
        states=SAFETY_STATES,
        initial=initial,
        transitions=SAFETY_TRANSITIONS,
    )
