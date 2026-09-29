# Medirover — Architecture

Status: reflects the implemented codebase (see [STATUS_MATRIX.md](STATUS_MATRIX.md)).
Everything below is **SIMULATION-VERIFIED** unless stated otherwise. No physical
hardware has been exercised in this build.

## 1. Big picture

```
┌──────────────────────────────┐        JSON over WebSocket         ┌───────────────────────────────┐
│  Frontend (no-build ES)      │ ◄────────────────────────────────► │  Backend (FastAPI, Python)    │
│  src/state, services,        │   /ws/state: snapshot, updates,    │                               │
│  components                  │   events, pong                     │  api/    routes + WS handlers │
└──────────────────────────────┘        /api/v1/* REST              │  core/   logging, health      │
                                                                               │  services/ node_manager, ingest,
┌──────────────────────────────┐                                              │           eventing, broadcaster,
│  Firmware (Python reference) │        JSON over WebSocket         ┌────────►│           supervisor │
│  motion_node / sensor_node   │ ◄────────────────────────────────► │  state/  node (connectivity)  │
│  common / hardware / comm    │   /ws/node: identify, heartbeat,   │           FSMs               │
│  simulation/ (SIMULATED)     │   telemetry, ack                   │  database/ models + alembic  │
└──────────────────────────────┘        REST (demo drives etc.)     │  models/ DB tables           │
                                                                               └─────────┬───────────┘
                                                                                         ▼
                                                                             SQLite (WAL) + files:
                                                                             data/, results/, recovery/
```

Single Python stack. "Firmware" is a Python reference implementation with a
hardware interface (`ISensor`, motors, power, safety input, status). Real MCU
drivers are a later milestone (M9/M10); until then the only hardware is
`firmware/hardware/simulated.py`.

## 2. Why these choices

| Decision | Rationale |
|---|---|
| Single Python stack (firmware as Python) | One language for protocol contracts; same `shared/` code runs on node and backend, so contract drift is a compile-time error. |
| JSON over WebSocket (not binary) | Human-debuggable, deterministic serialization, small message sizes. Protocol versioning stays in-band. |
| SQLite + WAL + alembic | Zero-ops storage for a single-device system; explicit migrations (the app never auto-migrates); isolated test DBs per run. |
| No-build ES-module frontend | No toolchain to rot; logic is unit-testable under `node --test`; the browser is a consumer of the same protocol. |
| Explicit state machines (shared/fsm) | Safety and connectivity transitions are data, exhaustively unit-tested; every transition is either legal or raises `FSMError`. |
| Canonical artifacts only | One bounded `results/test_history.jsonl`, one `recovery/PROJECT_STATE.json` — never a file per event (the 1.1 GB incident is the reason). |

## 3. Repository layout (as built)

```
backend/        FastAPI app
  api/          routes (REST + WS), error envelope, app factory, AppContext
  core/         logging config
  database/     models.py (6 tables), engine, migrations/ (alembic)
  models/       (re-export of database models for API convenience)
  schemas/      API response schemas
  services/     node_manager, telemetry_ingest, eventing, broadcaster,
                node_supervisor, ws_types (Protocols), audit
  state/        node_fsm (connectivity FSM factory)
  tests/        backend unit/integration tests
config/         development.yaml, simulation.yaml, testing.yaml, hardware.yaml
data/           runtime SQLite databases (gitignored; README explains)
docs/           this documentation
firmware/
  common/       node_context (NodeConfig), shared node plumbing
  communication/ client (NodeProtocolClient), ws_transport, simulated_transport
                (MemoryLink), retry/backoff
  hardware/     simulated.py (SimulatedHardware), interface definitions
  motion_node/  MotionNode: safety FSM owner, heartbeat/telemetry producers
  sensor_node/  SensorNode
  simulation/   demo_node (subprocess entry for scripts/demo.py)
  tests/        firmware tests + fake_backend (in-process protocol peer)
frontend/       index.html, css, js/src/{state,services,components}, tests/
recovery/       PROJECT_STATE.json/.md, artifact_manifest.json (canonical checkpoints)
results/        test_history.jsonl, storage_audit.json, persistence_validation.json,
                clean_checkout_validation.json (bounded, canonical)
scripts/        demo.py, clean_checkout.py
shared/         protocols (envelope, codec, registry, validator, sequence),
                schemas (node payloads), constants, types, errors,
                fsm (generic StateMachine + safety/connectivity factories),
                utils (ids, timeutil, asyncutil), events
tests/          cross-cutting tests: e2e vertical slice, disconnect/reconnect,
                failure injection, idempotency, crash recovery, API contract,
                protocol known-answer, FSM exhaustive, persistence/process boundary
tools/          project_state.py, storage.py, artifact_manifest.py (CLIs)
```

## 4. Data flow — one telemetry reading

1. `MotionNode` loop: `SimulatedHardware.step(dt)` → sensor read →
   `NodeProtocolClient` builds an envelope (strictly increasing `sequence`
   per connection, fresh `message_id` uuid4, aware-UTC timestamp) and sends it
   over the WebSocket transport.
2. `backend/api/ws_nodes.py` receives the raw frame → `NodeManager.handle()`.
3. `FrameValidator` (shared): MALFORMED → VERSION_MISMATCH → UNKNOWN_TYPE →
   INVALID → STALE (> 30 s clock skew) → VALID; then sequence check
   (DUPLICATE / OUT_OF_ORDER, recorded only when VALID).
4. VALID telemetry → `telemetry_ingest.ingest()` — batched
   `sqlite_insert ... ON CONFLICT DO NOTHING` on the unique key
   `(node_id, message_id, sensor_id)`: replays can never duplicate rows.
5. Runtime state updated in-memory (manager) + `node_runtime_state` row;
   `Broadcaster` pushes a `state_update` frame to every frontend subscriber.
6. Frontend `ws_client.js` → `store.js` (pure reducer) → `status_card.js`
   re-render.

Disconnect path: WS close → `NodeManager.on_disconnect()` → connectivity FSM
`WS_CLOSED` → OFFLINE → `NODE_DISCONNECTED` event persisted → forced
`state_update` to the UI. The supervisor independently watches heartbeat age
and escalates ONLINE → STALE → OFFLINE when frames stop arriving.

## 5. Failure domains

- **Node crash**: supervisor marks STALE then OFFLINE on heartbeat age; event
  recorded; UI shows OFFLINE. Reconnect re-identifies (same `node_id` → same
  registry row, no duplication — `nodes.id` is the identity key).
- **Backend restart**: DB is the source of truth for identity/telemetry/events;
  `node_runtime_state` rows are rehydrated at startup; nodes re-identify
  (identify resets the per-connection sequence tracker).
- **Replayed frames**: deduped by the unique constraint (idempotency tested).
- **Corrupt/crash mid-write**: project state uses atomic tmp+fsync+replace;
  orphan `.tmp` files are detected and removed by `project_state.py validate
  --recover`; SQLite transactions roll back incomplete writes.
