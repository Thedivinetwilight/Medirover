# Medirover — Architecture Map (SENSE → THINK → ACT)

Recovery snapshot, 2026-09-29, at commit **b0dd83f**. Written from the
source tree; `docs/ARCHITECTURE.md` remains the design narrative, this file
is the operational map a recovering engineer needs.

## Topology

```
 [SIMULATED node subprocess]                [BACKEND]                    [FRONTEND]
 firmware/simulation/demo_node.py           backend.main:app (uvicorn)   frontend/ (static)
   └─ MotionNode ─ SensorNode                ├─ /ws/node  ◄───────────────┐
       │  identify/heartbeat/telemetry/ack   ├─ /ws/state ───────────────►│ store.js (reducer)
       │  JSON envelopes over WebSocket      ├─ /api/v1/* REST ──────────►│ api.js
       └─ NodeProtocolClient                 │                            │ ws_client.js (polling
            (shared/protocols contracts)     │ NodeManager: identify,     │    fallback labeled)
          ▲                                  │ validate, FSM, broadcast   └─ status_card / event_feed
          │ SimulatedHardware (sim physics)  ├─ Supervisor: hb-age tick
          │ (IHardware contract)             ├─ TelemetryIngest (idempotent)
                                             └─ SQLite (WAL) via alembic   data/
```

Single Python stack; the same `shared/` contracts compile into both node and
backend, so protocol drift is a build-time failure, not a runtime surprise.

## SENSE

| Aspect | Where | Notes |
|---|---|---|
| Sensors | `firmware/hardware/simulated.py` (`SimulatedSensor`) behind `ISensor` | battery_voltage (V), encoder_left/right (ticks), motor_current (A); `quality: ok|degraded` per sample |
| Sensor health | `ISensor.healthy()` + `mark_degraded()` | degraded sensor ⇒ sample quality `degraded` ⇒ backend records `SENSOR_DEGRADED` WARNING event |
| Signal processing | none beyond reading + quality flag | no filtering/fusion exists (intentionally absent, not stubbed) |
| Telemetry | `MotionNode.telemetry_payload()` → `telemetry` frame → `backend/services/telemetry_ingest.py` | batch `sqlite_insert ... ON CONFLICT DO NOTHING` on `(node_id, message_id, sensor_id)` — replay-safe |
| Health/state data | `backend/services/node_manager.py` runtime dict + `node_runtime_state` table | connectivity, safety_state, source_kind, last_heartbeat_at, last_telemetry per sensor, battery_voltage, uptime_s |
| Health endpoint | `GET /api/v1/health` | status, environment, source_kind=SIMULATED, protocol_version, DB reachability |

## THINK

| Aspect | Where | Notes |
|---|---|---|
| Decision logic | `firmware/motion_node/node.py` loop | heartbeat every `heartbeat_interval_s`; telemetry every `telemetry_interval_s`; demo drive cycle every `drive_every_s` (simulation profile only; hardware profile: 0) |
| State machines | `shared/fsm/base.py` (generic `StateMachine[S,E]`), `shared/safety/machine.py` (safety), `backend/state/node_fsm.py` (connectivity) | illegal transitions raise `FSMError(allowed=...)` — never a silent no-op; exhaustive unit tests |
| Safety FSM | SAFE→READY(INIT_OK); READY⇄ACTIVE(COMMAND_ACCEPT/COMMAND_COMPLETE); ANOMALY⇒WARNING (idle) or FAULT (moving); FAULT→RECOVERY(CLEAR_REQUESTED)→READY|FAULT; **E_STOP from every state** → EMERGENCY_STOP; single exit E_STOP_RELEASED→RECOVERY | the node refuses motion commands unless READY |
| Connectivity FSM | DISCONNECTED→CONNECTING(WS_CONNECTED on identify)→ONLINE(IDENTIFY_OK); ONLINE→STALE(HEARTBEAT_LATE)→ONLINE(HEARTBEAT_OK); STALE/ONLINE→OFFLINE(timeout/closed) | supervisor tick (default 0.2 s) is the crash backstop; `on_disconnect` persists the FSM result |
| Protocol validation | `shared/protocols/validator.py` | deterministic order: MALFORMED→VERSION_MISMATCH→UNKNOWN_TYPE→INVALID→STALE(>30 s)→VALID, then DUPLICATE/OUT_OF_ORDER |
| AI/ML, navigation, perception, task planning | **absent** | no such code exists; not stubs — simply not built (would be new milestones) |

## ACT

| Aspect | Where | Notes |
|---|---|---|
| Motor commands | `IMotorController.set_speed(left_mps, right_mps)` / `stop()` | implemented only by `SimulatedHardware._SimMotors` (deterministic ramp physics); real driver = M8 skeleton → M10 physical |
| Arm/servo control | **absent** | no arm/servo code in the repository |
| Actuator abstraction | `firmware/hardware/interfaces.py` | `IMotorController`, `IPowerMonitor`, `ISafetyInput`, `IStatusOutput`, `IStorage`, `ICommunication` — node logic depends only on these |
| Safety gates | motion node loop checks `safety.state` before commanding; E_STOP drives `stop()` + EMERGENCY_STOP | see `firmware/motion_node/node.py`; gates are FSM-enforced, not flag-based |

## Cross-cutting

| Aspect | Where |
|---|---|
| Emergency stop | safety FSM (above) + `ISafetyInput.e_stop_engaged()`; **physical hardwired E-stop does not exist yet — software path only** (`docs/SAFETY.md` M10 checklist) |
| Watchdogs | `NodeSupervisor` (heartbeat-age escalation), client-side reconnect with exponential backoff, identify timeout, malformed-frame circuit breaker (3× → close 1008), client-frame limit (5× → close 1008) |
| Connection handling | WS per role (`/ws/node`, `/ws/state`); identify-once per connection; sequence resets per connection; clean close ⇒ OFFLINE + event; crash ⇒ supervisor escalation |
| Fault handling | safety FSM FAULT/RECOVERY, `SENSOR_DEGRADED` events, `faults` table (currently written by safety transitions via events), error envelope on all HTTP errors |
| Simulation mode | `config/simulation.yaml`, `source_kind=SIMULATED` on every state, UI chip; simulation parameters explicitly placeholder-labeled |
| Hardware abstraction | `firmware/hardware/interfaces.py`; only simulated implementation exists |
| Persistence | SQLite WAL; alembic-only migrations; app refuses to start on unmigrated DB; canonical bounded artifacts (`recovery/`, `results/`) |
| API boundaries | REST `/api/v1/*` (typed responses, error envelope), WS `/ws/*` (protocol frames) |
| Frontend↔backend | WS snapshot/updates/events with REST polling fallback (adaptive 1→15 s, labeled `polling` in UI) |
| Firmware↔backend | same JSON protocol both directions; registry in `shared/protocols/registry.py` |

## Failure domains (as implemented)

- Node crash → supervisor STALE→OFFLINE + event; reconnect re-identifies (single registry row).
- Backend restart → DB rehydration; nodes re-identify.
- Replay → idempotent ingest (unique constraint).
- Mid-write crash → atomic checkpoint (tmp+fsync+replace) + orphan cleanup; SQLite rollback; verified by `tests/test_crash_recovery.py` and `tests/persistence/`.
