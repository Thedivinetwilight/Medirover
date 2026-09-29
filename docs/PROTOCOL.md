# Medirover — Node Protocol

Status: IMPLEMENTED, UNIT-TESTED (known-answer matrix in
`tests/test_protocol_validation.py`), SIMULATION-VERIFIED (e2e over real
WebSockets). Transport: JSON text frames over WebSocket.

## 1. Envelope

Every frame is a single JSON object:

| Field | Type | Rules |
|---|---|---|
| `protocol_version` | int | current value: see `shared/constants.py` |
| `message_version` | int | message-format version |
| `message_type` | string | from the registry (§3); unknown → `UNKNOWN_TYPE` |
| `message_id` | string (uuid4) | unique per frame; dedup key |
| `sequence` | int | **strictly increasing per connection**; resets to a new series on reconnect (after identify) |
| `timestamp` | string | aware-UTC ISO-8601 |
| `node_id` | string | owning node (empty for some server→client frames) |
| `payload` | object | typed per `message_type` (`shared/schemas/node.py`); `extra="forbid"` — unknown fields make the frame INVALID |

Validation is strict by design: `extra="forbid"` on every payload model, and
the validator never guesses.

## 2. Validation order (deterministic, unit-tested)

```
parse JSON            → fail: MALFORMED
protocol_version match→ fail: PROTOCOL_VERSION_MISMATCH
message_type known    → fail: UNKNOWN_TYPE
payload schema valid  → fail: INVALID
clock skew ≤ 30 s     → fail: STALE
                    → VALID
sequence check (VALID frames only) → DUPLICATE | OUT_OF_ORDER | (accepted)
```

`DUPLICATE` and `OUT_OF_ORDER` are **recorded, not fatal** (events are logged,
the frame is not double-applied; ingestion is idempotent regardless).

## 3. Message registry (`shared/protocols/registry.py`)

| Direction | Type | Purpose |
|---|---|---|
| node → backend | `identify` | node_id, node_name, node_type, firmware_version, capabilities |
| node → backend | `heartbeat` | safety_state, uptime_s, battery_voltage |
| node → backend | `telemetry` | tick + samples[{sensor_id, value, unit, quality}] |
| node → backend | `ack` | acknowledgment of a backend message |
| backend → node | `welcome` | identification accepted (carries connection parameters) |
| backend → node | `reject` | reason + error_code; sent for invalid/malformed frames |
| backend → node | `ping` | liveness probe (pong is implicit via heartbeat flow) |
| backend → client | `state_snapshot` | all node states + recent events (on subscribe) |
| backend → client | `state_update` | one node's new state |
| backend → client | `event` | an `events` table row, pushed |
| backend → client | `pong` | answer to client ping |
| client → backend | `subscribe` | node_ids filter (empty = all) |
| client → backend | `ping` | client liveness |

## 4. Connection lifecycle (node side)

```
CONNECT ──► IDENTIFY (once) ──► WELCOME ──► ONLINE loop (heartbeat/telemetry)
                     │              │
                     └── REJECT ◄───┘   (invalid frame before identify → reject, no state change)
```

- **Identify exactly once per connection.** A second identify on the same
  connection is rejected (the per-connection sequence tracker resets only on a
  new identify after reconnect).
- **Invalid identify → `reject`**, connection stays open but not identified;
  no node state is created.
- **3 consecutive MALFORMED frames → server closes with 1008**
  (policy constant `MALFORMED_LIMIT`). Malformed frames below the limit receive
  a `reject` with `error_code: PROTOCOL_MALFORMED`.
- Oversized frame (> `max_frame_bytes`, default 16 384) counts as malformed.
- Close codes used: `1008` protocol policy violation, `1011` internal error,
  `1013` try-again-later (connection limit reached).

## 5. Sequence semantics

- `sequence` is a per-connection monotonic counter starting at 0.
- Reconnect = new connection = new sequence series (no cross-connection
  ordering is claimed).
- `DUPLICATE`: same `sequence` seen twice → frame dropped (event recorded).
- `OUT_OF_ORDER`: sequence lower than last-seen (gap beyond duplicate) →
  frame dropped (event recorded). Because transport is WebSocket (TCP), these
  are defenses against application-level replays/bugs, not packet loss.

## 6. Clocks and staleness

- All timestamps are aware-UTC ISO-8601.
- A frame whose `timestamp` is more than **30 s** away from the backend clock
  is `STALE` (rejected). Node→backend skew is one-sided by design.
- Heartbeat *silence* (not frame age) drives connectivity escalation in the
  supervisor: `stale_after_s`, then `offline_after_s` (environment-configured;
  testing profile: 0.6 s / 1.2 s).
