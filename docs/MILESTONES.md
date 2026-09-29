# Medirover — Milestones

Status labels and honesty rules per the rebuild directive. A milestone is
"complete" only when its acceptance tests pass **and** the work is committed
to GitHub. Current position as of 2026-09-29: **M7 in progress** (tools exist
and are exercised by tests; `clean_checkout.py` first local run is the gate).

| ID | Milestone | Acceptance test | Status |
|---|---|---|---|
| M0 | Clean foundation: repo structure, gates (ruff/mypy/pytest/CI), artifact discipline | CI green on empty skeleton; storage audit passes | COMPLETE |
| M1 | Shared contracts: envelope, validator, registry, sequence, FSM engine, errors | Known-answer protocol matrix; exhaustive FSM unit tests | COMPLETE (UNIT-TESTED) |
| M2 | Backend skeleton: config, DB + explicit migrations, app factory, error envelope | API contract tests on a real server + isolated DB | COMPLETE (INTEGRATION-TESTED) |
| M3 | Node manager + ingestion + events + broadcast + supervisor | Failure-injection + idempotency + supervisor tests | COMPLETE (SIMULATION-VERIFIED) |
| M4 | Frontend core: store, WS client (polling fallback), API client, status card, event feed | `node --test` logic tests; contract of WS frames | COMPLETE (UNIT-TESTED) |
| M5 | **First vertical slice**: SIMULATED NODE → identify → heartbeat → telemetry → backend → DB → API → frontend live status; disconnect → OFFLINE + event + UI; reconnect → recovery | `tests/test_e2e_vertical_slice.py` + `tests/test_disconnect_reconnect.py` over real uvicorn + real WebSockets | COMPLETE (SIMULATION-VERIFIED) |
| M6 | Failure & edge behavior: malformed/unknown/stale/duplicate/out-of-order, degraded sensors, crash recovery, process-boundary persistence | `tests/test_failure_injection.py`, `test_crash_recovery.py`, `test_idempotency.py`, `tests/persistence/` | COMPLETE (SIMULATION-VERIFIED) |
| M7 | Tooling & recovery: project state checkpoint, artifact manifest, storage audit, clean-checkout validation | Tools unit-covered; `scripts/clean_checkout.py` local run green → `results/clean_checkout_validation.json` | IN PROGRESS |
| M8 | Hardware abstraction hardening + real driver skeletons (motors, encoders, E-stop, battery, indicators) with safety interlocks | Driver unit tests against injected fault conditions | NOT-STARTED |
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
