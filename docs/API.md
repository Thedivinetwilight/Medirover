# Medirover — API

Status: IMPLEMENTED, INTEGRATION-TESTED (contract tests in
`tests/test_api_contract.py`; live-server e2e in `tests/test_e2e_vertical_slice.py`).

Base: `http://<host>:<port>` — REST under `/api/v1`, WebSocket under `/ws/*`,
frontend served at `/` (static mount of `frontend/`).

## 1. REST

| Method & path | Returns | Notes |
|---|---|---|
| `GET /api/v1/health` | `{status, environment, protocol_version, db, uptime_s, nodes_online}` | liveness + honest environment label |
| `GET /api/v1/nodes` | `[{node_id, name, node_type, capabilities, state{...}}]` | `state` = live runtime state |
| `GET /api/v1/nodes/{node_id}` | `{node, state, recent_events}` | 404 with error envelope if unknown |
| `GET /api/v1/nodes/{node_id}/telemetry?limit=&sensor_id=` | `[{node_id, sensor_id, value, unit, quality, message_id, received_at}]` | newest first; `limit` 1..1000 |
| `GET /api/v1/nodes/{node_id}/events?limit=` | `[{event_id, event_type, severity, message, state, timestamp, node_id}]` | |
| `GET /api/v1/events?limit=&node_id=&severity=` | same rows, global feed | |
| `GET /api/v1/faults?node_id=` | `[{fault_id, kind, detail, occurred_at, resolved_at, node_id}]` | |

### Node state object

```json
{
  "connectivity": "ONLINE",            // DISCONNECTED|CONNECTING|ONLINE|STALE|OFFLINE
  "safety_state": "READY",             // SAFE|READY|ACTIVE|WARNING|FAULT|EMERGENCY_STOP|RECOVERY
  "source_kind": "SIMULATED",          // SIMULATED until real hardware exists (M10)
  "last_heartbeat_at": "2026-09-29T03:00:00+00:00",
  "last_telemetry": {"battery_voltage": {"value": 8.1, "unit": "V", "quality": "ok", "at": "..."}, "...": "..."},
  "battery_voltage": 8.1,
  "uptime_s": 123.4,
  "updated_at": "..."
}
```

`source_kind` is part of every state — the UI shows SIMULATED explicitly and
never presents simulated data as physical measurement.

### Error envelope (all non-2xx JSON responses)

```json
{
  "code": "NOT_FOUND",                 // stable machine code
  "message": "node 'x' is not known",
  "category": "validation|not_found|internal|protocol|safety|storage",
  "severity": "WARNING",
  "source": "backend.api",
  "recoverable": true,
  "recommended_action": "check the node_id",
  "details": {}
}
```

Known codes: `NOT_FOUND` (404), `VALIDATION_FAILED` (422),
`PROTOCOL_*` (WS rejects), `INTERNAL` (500, no stack traces leak).

## 2. WebSocket — `/ws/state` (frontend)

Server → client: `state_snapshot` (on connect: all nodes + recent events),
`state_update` (per node, on change), `event` (each recorded event), `pong`.
Client → server: `subscribe {node_ids: [...]}` (empty/omitted = all nodes),
`ping`. Bad frames are counted; 5 invalid client frames → close 1008.

The frontend falls back to REST polling when the socket is down (adaptive
1→15 s backoff) — labeled `polling` in the UI, never masquerading as live.

## 3. WebSocket — `/ws/node` (firmware)

See [PROTOCOL.md](PROTOCOL.md). The endpoint is a thin transport: all
protocol/state logic is in `NodeManager` (unit-testable without sockets).

## 4. Conventions

- All times aware-UTC ISO-8601. All ids strings. Node identity = `node_id`
  (stable across reconnects; registry row updated on re-identify, never
  duplicated).
- The backend never auto-migrates: it refuses to start unless
  `alembic current == head` (run `make migrate`).
- No authentication in this build — see [SECURITY.md](SECURITY.md) known gaps.
