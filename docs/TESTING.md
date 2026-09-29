# Medirover — Testing

Status: suite is green at the current commit — **185 Python tests + 4
frontend tests**. All e2e tests run against a **real uvicorn server, real
WebSockets, and a real (ephemeral) SQLite database**; nothing e2e is mocked
at the transport or DB layer.

## Layers

| Layer | Where | What it proves |
|---|---|---|
| Protocol known-answer | `tests/test_protocol_validation.py` | Exact outcomes for VALID / INVALID / MALFORMED / STALE / DUPLICATE / OUT_OF_ORDER / UNKNOWN_TYPE / PROTOCOL_VERSION_MISMATCH |
| FSM exhaustive | `tests/test_safety_fsm.py`, `tests/test_connectivity_fsm.py` | Every legal transition; illegal transitions raise `FSMError` (parametrized over the full table) |
| Backend unit/integration | `backend/tests/` | Config validation, supervisor stale/offline escalation, ingest idempotency |
| Firmware unit | `firmware/tests/` (with `fake_backend.py`) | Client protocol behavior (identify-once, seq reset, reconnect), node payload shape |
| API contract | `tests/test_api_contract.py` | Response shapes, error envelope (404/422), frontend index served |
| **E2E vertical slice** | `tests/test_e2e_vertical_slice.py` | M5 acceptance: node → identify → heartbeat → telemetry → DB → API → frontend WS live status |
| Disconnect/reconnect | `tests/test_disconnect_reconnect.py` | Clean close → OFFLINE + event + UI state; reconnect → ONLINE; single registry row; 2× NODE_IDENTIFIED |
| Failure injection | `tests/test_failure_injection.py` | Raw-socket abuse: malformed×3 → close 1008; unknown type; version mismatch; stale; duplicate; out-of-order; degraded sensor → SENSOR_DEGRADED event |
| Idempotency | `tests/test_idempotency.py` | Replayed ingest → no duplicate rows; state tooling → no artifact multiplication; audit produces one bounded file |
| Crash recovery | `tests/test_crash_recovery.py` | Orphan `.tmp` cleanup; crashed writer; SQLite uncommitted rollback; no duplicate artifacts |
| Process boundary | `tests/persistence/test_process_boundary.py` | Checkpoint written by process A, validated/shown/set by processes B/C/D; `results/persistence_validation.json` |

## Running

```bash
make check              # ruff + mypy + pytest (backend + firmware + root)
make test-frontend      # node --test 'frontend/tests/**/*.test.mjs'
.venv/bin/python -m pytest tests/test_e2e_vertical_slice.py   # single file
```

- pytest config: `asyncio_mode = "auto"`, testpaths `backend/tests`,
  `firmware/tests`, `tests`. Each e2e test gets a fresh `tmp_path` SQLite DB
  via `MEDIROVER_DB_URL` + alembic, and a uvicorn server on an ephemeral
  port (no fixed ports → no flakiness from port collisions).
- Every session appends **one** bounded line to `results/test_history.jsonl`
  (capped at 500 lines, includes the git commit) — never one file per run.

## Timing notes

The testing profile uses fast constants (hb 0.2 s / stale 0.6 s / offline
1.2 s / supervisor 0.05 s) so escalation paths are exercised in seconds, not
minutes. Full suite ≈ 20 s local.

## What the suite does NOT cover (honest)

- Visual/browser rendering (the e2e asserts the WS payload the UI consumes;
  no headless-browser test exists yet).
- Real hardware of any kind (M10).
- Long-run soak / field conditions (M11).
