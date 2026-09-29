# Medirover — Milestones

Status labels and honesty rules per the rebuild directive. A milestone is
"complete" only when its acceptance tests pass **and** the work is committed
to GitHub. Current position as of 2026-09-29: **M8 COMPLETE** — real driver
skeletons (`firmware/hardware/real/`) with safety interlocks, fault-injected
deterministically against `MemoryBoard`; `source_kind` propagated node →
backend → persistence. Physical hardware remains UNVERIFIED (M9/M10).

| ID | Milestone | Acceptance test | Status |
|---|---|---|---|
| M0 | Clean foundation: repo structure, gates (ruff/mypy/pytest/CI), artifact discipline | CI green on empty skeleton; storage audit passes | COMPLETE |
| M1 | Shared contracts: envelope, validator, registry, sequence, FSM engine, errors | Known-answer protocol matrix; exhaustive FSM unit tests | COMPLETE (UNIT-TESTED) |
| M2 | Backend skeleton: config, DB + explicit migrations, app factory, error envelope | API contract tests on a real server + isolated DB | COMPLETE (INTEGRATION-TESTED) |
| M3 | Node manager + ingestion + events + broadcast + supervisor | Failure-injection + idempotency + supervisor tests | COMPLETE (SIMULATION-VERIFIED) |
| M4 | Frontend core: store, WS client (polling fallback), API client, status card, event feed | `node --test` logic tests; contract of WS frames | COMPLETE (UNIT-TESTED) |
| M5 | **First vertical slice**: SIMULATED NODE → identify → heartbeat → telemetry → backend → DB → API → frontend live status; disconnect → OFFLINE + event + UI; reconnect → recovery | `tests/test_e2e_vertical_slice.py` + `tests/test_disconnect_reconnect.py` over real uvicorn + real WebSockets | COMPLETE (SIMULATION-VERIFIED) |
| M6 | Failure & edge behavior: malformed/unknown/stale/duplicate/out-of-order, degraded sensors, crash recovery, process-boundary persistence | `tests/test_failure_injection.py`, `test_crash_recovery.py`, `test_idempotency.py`, `tests/persistence/` | COMPLETE (SIMULATION-VERIFIED) |
| M7 | Tooling & recovery: project state checkpoint, artifact manifest, storage audit, clean-checkout validation | Tools unit-covered; `scripts/clean_checkout.py` local-clone run green → `results/clean_checkout_validation.json` (all 10 steps ok, exit 0) | COMPLETE (local-clone verified) |
| M8 | Hardware abstraction hardening + real driver skeletons (motors, encoders, E-stop, battery, indicators) with safety interlocks | Driver unit tests against injected fault conditions | COMPLETE (UNIT-TESTED, fault-injected; physical verification UNVERIFIED — M9/M10) |
| M9 | Real MCU firmware port (motion + sensor nodes) with the same shared protocol | Boot → identify → heartbeat on real node, integration bench | NOT-STARTED |
| M10 | Physical integration: first real node online; E-stop physically exercised; safety verified on hardware | HARDWARE-VERIFIED checklist signed off | NOT-STARTED |
| M11 | Field operation: connectivity under real conditions, telemetry trends, fault history, long-run soak | FIELD-VERIFIED log + soak report | NOT-STARTED |
| M12 | Release hardening: security review closure (auth/TLS), docs final, release artifact | Security + docs review complete | NOT-STARTED |

## M5 acceptance traceability (the first vertical slice)

| Requirement | Test that proves it |
|---|---|
| Node identifies and becomes ONLINE | `test_vertical_slice_live_status` (step 1–2) |
| Telemetry flows into the database and API | same (step 3: ≥2 rows, `battery_voltage` present) |
| Frontend gets snapshot + live updates | same (step 4: `state_snapshot` + `state_update`/`event` frames, node ONLINE/READY in snapshot) |
| Events recorded (identify) | same (step 5: `NODE_IDENTIFIED` in event feed) |
| Node registry persisted | same (step 6: name/type/capabilities from DB) |
| Disconnect → OFFLINE + event + UI state | `test_disconnect_marks_offline_and_reconnect_recovers` (steps 2–4) |
| Reconnect same identity → recovery, no duplicate rows | same (steps 5–8: single registry row, telemetry resumes, 2× `NODE_IDENTIFIED`) |

## M8 acceptance traceability (hardware abstraction hardening)

| Requirement | Test that proves it |
|---|---|
| No motion before explicit enable (rules 4/10) | `test_no_motion_before_enable`, `test_enable_allows_motion_with_direction` |
| E-stop: immediate, latching, software can never clear it while asserted (rules 5/6) | `test_estop_latch_engages_and_holds`, `test_estop_latch_cannot_be_cleared_by_software_while_asserted`, `test_estop_blocks_commands_mid_motion` |
| Zero-velocity stop bypasses every interlock (rule 6) | `test_stop_bypasses_all_interlocks`, `test_facade_estop_auto_stops_motors_and_latches` |
| Full E-stop operator lifecycle (press → release → acknowledge → re-enable) | `test_facade_estop_full_lifecycle` |
| Over-current latching fault + explicit clear + re-enable (rule 5/10) | `test_overcurrent_fault_latches_and_clears`, `test_facade_overcurrent_trips_on_step` |
| Unknown readings are UNKNOWN, never guessed (rule 11) | `test_battery_states_and_unknown`, `test_facade_sensors_never_fabricate_readings` |
| Zero-velocity / stall verification from encoders | `test_encoder_velocity_zero_and_stall` |
| Node reports its own origin; label never relabelled (rule 13) | `test_real_hardware_node_identifies_as_hardware`, `test_facade_defaults_and_label_policy`, `backend/tests/test_source_kind.py` (identify → runtime → DB, restart persistence, legacy default) |
| Hardware profile never self-issues motion (rule 4/10) | `test_hardware_profile_locks_automatic_drive_off` |

Honesty boundary: all of the above runs against `MemoryBoard` (deterministic
in-memory board I/O). **No physical motor, encoder, E-stop button, or battery
has been exercised** — that is M9 (MCU port) / M10 (physical integration).
