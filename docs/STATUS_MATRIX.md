# Medirover — Status Matrix

Status labels (per rebuild directive):
`NOT-STARTED, STUB, PARTIAL, IMPLEMENTED, UNIT-TESTED, INTEGRATION-TESTED,
SIMULATION-VERIFIED, HARDWARE-VERIFIED, FIELD-VERIFIED`.
Simulation verification is **never** reported as hardware verification.
Current date of this matrix: 2026-09-29 (rebuild commit series).

| Component | Status | Evidence |
|---|---|---|
| Shared protocol (envelope, codec, registry, validator, sequence) | SIMULATION-VERIFIED | known-answer matrix `tests/test_protocol_validation.py`; e2e over real WS |
| Safety FSM | UNIT-TESTED (exhaustive transitions + invariants) | `tests/test_safety_fsm.py` |
| Connectivity FSM | UNIT-TESTED (exhaustive) + INTEGRATION-TESTED | `tests/test_connectivity_fsm.py`, disconnect/reconnect e2e |
| Backend API (REST) | INTEGRATION-TESTED | `tests/test_api_contract.py` (real uvicorn + real SQLite) |
| Node manager (identify/heartbeat/telemetry/reject/malformed) | SIMULATION-VERIFIED | e2e + failure-injection tests |
| Telemetry ingestion + idempotency | INTEGRATION-TESTED | `tests/test_idempotency.py` (replayed frames → no dup rows) |
| Eventing + broadcaster | INTEGRATION-TESTED | contract + e2e (UI receives snapshot/updates/events) |
| Node supervisor (stale/offline backstop) | UNIT-TESTED + INTEGRATION-TESTED | `backend/tests/test_supervisor.py`, disconnect e2e |
| Migrations (alembic, explicit) | INTEGRATION-TESTED | every test session migrates a fresh isolated DB |
| Frontend state store + WS client logic | UNIT-TESTED (node --test) | `frontend/tests/store.test.mjs` (4 tests) |
| Frontend UI rendering in a real browser | SIMULATION-VERIFIED (via WS e2e) / UNVERIFIED (visual) | e2e asserts the WS payload the UI consumes; no browser render test |
| Simulated hardware (SimulatedHardware) | SIMULATION-VERIFIED | deterministic physics, seeded RNG |
| Motion node (Python reference firmware) | SIMULATION-VERIFIED | e2e identify→ONLINE→telemetry→OFFLINE→reconnect |
| Sensor node (Python reference firmware) | UNIT-TESTED / PARTIAL | implemented + unit tests; not yet exercised in the e2e slice |
| Demo script (scripts/demo.py) | IMPLEMENTED / SIMULATION-VERIFIED-equivalent path | same server+node path covered by e2e; script itself not run in CI |
| Clean-checkout validation script | IMPLEMENTED / UNVERIFIED (until first local run) | `scripts/clean_checkout.py`; output → `results/clean_checkout_validation.json` |
| Real hardware drivers (motors, encoders, E-stop wiring, battery) | NOT-STARTED | `firmware/hardware/` defines interfaces; only `simulated.py` exists |
| MCU firmware port | NOT-STARTED | milestone M9 |
| Authentication / TLS | NOT-STARTED | known gap, see SECURITY.md |
| Physical motion / E-stop on real hardware | NOT-STARTED — **no physical verification has been performed in this build** | — |

Test totals at this commit: **185 Python tests passed + 4 frontend tests
passed** (full suite ≈ 20 s local). Lint (ruff) and types (mypy, 86 files)
clean.
