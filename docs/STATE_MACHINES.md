# Medirover — State Machines

Status: IMPLEMENTED, UNIT-TESTED **exhaustively** (every legal transition and a
sample of every illegal one, `tests/test_safety_fsm.py` and
`tests/test_connectivity_fsm.py`).

Generic engine: `shared/fsm/base.py` — `StateMachine[S, E]` with a
`(state, event) → state` table. Unknown/illegal pairs raise
`FSMError(allowed=[...])` — a transition can never silently be a no-op.

## 1. Safety FSM (owned by the motion node)

States: `SAFE, READY, ACTIVE, WARNING, FAULT, EMERGENCY_STOP, RECOVERY`

| From | Event | To |
|---|---|---|
| SAFE | INIT_OK | READY |
| SAFE | E_STOP | EMERGENCY_STOP |
| READY | COMMAND_ACCEPT | ACTIVE |
| READY | ANOMALY | WARNING |
| READY | FAULT | FAULT |
| READY | E_STOP | EMERGENCY_STOP |
| ACTIVE | COMMAND_COMPLETE | READY |
| ACTIVE | ANOMALY | FAULT (anomaly while moving ⇒ halt) |
| ACTIVE | E_STOP | EMERGENCY_STOP |
| WARNING | ANOMALY_CLEAR | READY |
| WARNING | FAULT | FAULT |
| WARNING | E_STOP | EMERGENCY_STOP |
| FAULT | CLEAR_REQUESTED | RECOVERY |
| FAULT | E_STOP | EMERGENCY_STOP |
| RECOVERY | RECOVERY_OK | READY |
| RECOVERY | RECOVERY_FAILED | FAULT |
| RECOVERY | E_STOP | EMERGENCY_STOP |
| EMERGENCY_STOP | E_STOP_RELEASED | RECOVERY |

Source: `shared/safety/machine.py` (SAFETY_TRANSITIONS, verbatim).

Safety invariants (tested):
- **E_STOP dominates**: from every state except EMERGENCY_STOP itself,
  E_STOP → EMERGENCY_STOP (motors are commanded to stop on the node side;
  the FSM records the state).
- **Single exit**: EMERGENCY_STOP leaves only via E_STOP_RELEASED → RECOVERY,
  then RECOVERY_OK → READY. There is no shortcut back to ACTIVE.
- Initial state is `SAFE`; a node only becomes `READY` after its startup
  self-check (`INIT_OK`).

## 2. Connectivity FSM (owned by the backend, per node)

States: `DISCONNECTED, CONNECTING, ONLINE, STALE, OFFLINE`

| From | Event | To |
|---|---|---|
| DISCONNECTED | WS_CONNECTED | CONNECTING |
| OFFLINE | WS_CONNECTED | CONNECTING |
| CONNECTING | IDENTIFY_OK | ONLINE |
| CONNECTING | IDENTIFY_FAILED | DISCONNECTED |
| CONNECTING | WS_CLOSED | DISCONNECTED |
| ONLINE | HEARTBEAT_LATE | STALE |
| ONLINE | HEARTBEAT_OK | ONLINE (explicit idempotent no-op) |
| ONLINE | HEARTBEAT_TIMEOUT | OFFLINE |
| ONLINE | WS_CLOSED | OFFLINE |
| STALE | HEARTBEAT_OK | ONLINE |
| STALE | HEARTBEAT_TIMEOUT | OFFLINE |
| STALE | WS_CLOSED | OFFLINE |

Source: `backend/state/node_fsm.py` (CONNECTIVITY_TRANSITIONS, verbatim).
`WS_CONNECTED` is applied when an *identify* for a known node is received —
a raw socket connect does not yet name the node.

Rules of use:
- The FSM is the single source of truth for connectivity; runtime state and
  the UI are always written **from** an FSM result (`on_disconnect`,
  heartbeat handling, supervisor tick). Persisting the pre-transition value
  was a real bug found during testing and is covered by
  `tests/test_disconnect_reconnect.py`.
- `STALE` means "frames stopped arriving but the connection may be alive"
  (heartbeat age > `stale_after_s`); `OFFLINE` means "no connection and/or
  heartbeat age > `offline_after_s`".
- The supervisor scans every `supervisor_scan_s` (testing: 0.05 s) and is the
  backstop for crashes that never send a clean close.

## 3. Event model

State-machine-driven events are recorded in the `events` table. Current
`event_type` values (from `grep` over the services):
`NODE_IDENTIFIED, NODE_DISCONNECTED, NODE_OFFLINE, NODE_RECOVERED,
NODE_STALE, SENSOR_DEGRADED, PROTOCOL_MALFORMED, PROTOCOL_MALFORMED_LIMIT,
PROTOCOL_INVALID, PROTOCOL_DUPLICATE, PROTOCOL_OUT_OF_ORDER` — plus
`PROTOCOL_<OUTCOME>` for the remaining validation outcomes
(`PROTOCOL_STALE, PROTOCOL_UNKNOWN_TYPE, PROTOCOL_VERSION_MISMATCH`).
Each row carries severity (INFO/WARNING/ERROR/CRITICAL) and a JSON `state`
snapshot. Events are pushed to the UI via the state WebSocket and are
queryable via `GET /api/v1/events`.
