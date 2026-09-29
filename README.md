# Medirover

A multi-node rover system: a Python backend (FastAPI + SQLite + WebSocket),
a no-build frontend dashboard, and Python reference firmware for motion and
sensor nodes speaking a strict, versioned JSON protocol. This repository is a
**clean rebuild** from 2026-09-29 — no legacy code was carried forward, and
the status of every component is documented with honest labels (simulation
is never claimed as hardware verification).

## Current status (honest)

| | |
|---|---|
| Vertical slice (simulated) | ✅ SIMULATION-VERIFIED — simulated node → identify → heartbeat → telemetry → backend → database → API → dashboard live status; disconnect → OFFLINE + event + UI; reconnect → recovery |
| Test suite | ✅ 185 Python + 4 frontend tests, green (≈20 s) |
| Lint / types | ✅ ruff clean, mypy clean (86 files) |
| Real hardware | ⬜ NOT-STARTED (milestones M8–M10) — no physical verification exists |
| Auth / TLS | ⬜ NOT-STARTED (milestone M12) — trusted-local-network assumption, see `docs/SECURITY.md` |

Full component table: [`docs/STATUS_MATRIX.md`](docs/STATUS_MATRIX.md) ·
Milestones: [`docs/MILESTONES.md`](docs/MILESTONES.md)

## Quickstart

Requires Python 3.11 and Node 22.

```bash
make install        # venv + editable install (once)
make migrate        # apply the alembic migration (explicit; app never auto-migrates)
make demo           # backend on :8000 + simulated node (subprocess)
```

Open **http://localhost:8000/** — the dashboard shows the simulated node
`motion-01` coming ONLINE with live telemetry and events. The simulation
profile drops the link for 4 s every 30 s (watch OFFLINE → recovery) and
runs a drive cycle every 15 s. Ctrl-C stops everything cleanly.

```bash
make check          # ruff + mypy + full pytest
make test-frontend  # node --test 'frontend/tests/**/*.test.mjs'
make clean-checkout # full from-scratch validation → results/clean_checkout_validation.json
```

## Architecture in one paragraph

Nodes (motion/sensor, currently simulated) connect to the backend over
WebSocket and speak a strict JSON envelope protocol: identify once, then
heartbeats and telemetry with strictly-increasing per-connection sequence
numbers. The backend validates every frame with an explicit outcome
(VALID / INVALID / MALFORMED / STALE / DUPLICATE / OUT_OF_ORDER /
UNKNOWN_TYPE / PROTOCOL_VERSION_MISMATCH), stores telemetry idempotently in
SQLite, tracks each node through an explicit **connectivity FSM**, and pushes
state snapshots, updates, and events to the dashboard over a second
WebSocket (with polling fallback). The motion node owns a **safety FSM**
(E_STOP reachable from any state, single recovery path). Details:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/PROTOCOL.md`](docs/PROTOCOL.md),
[`docs/STATE_MACHINES.md`](docs/STATE_MACHINES.md),
[`docs/API.md`](docs/API.md).

## Repository layout

```
backend/    FastAPI app (api, core, database+alembic, services, state, tests)
frontend/   no-build ES dashboard (state store, ws client, components, tests)
firmware/   Python reference firmware (common, communication, hardware,
            motion_node, sensor_node, simulation, tests)
shared/     the contracts: protocol, schemas, constants, types, errors,
            fsm, safety, events, utils
config/     testing / development / simulation / hardware profiles
data/       runtime SQLite (gitignored)
docs/       architecture, protocol, state machines, API, status matrix,
            milestones, artifacts/retention, security, operations, testing,
            development, safety, legacy knowledge map
scripts/    demo.py, clean_checkout.py
tools/      project_state.py, storage.py, artifact_manifest.py
tests/      cross-cutting tests incl. the M5 e2e vertical slice
recovery/   canonical checkpoint: PROJECT_STATE.json/.md, artifact_manifest.json
results/    bounded canonical results (test history, audits, validations)
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data flow, failure domains
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — envelope, registry, validation order, lifecycle
- [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md) — safety + connectivity tables (verbatim from code)
- [docs/API.md](docs/API.md) — REST + WebSocket API, error envelope
- [docs/STATUS_MATRIX.md](docs/STATUS_MATRIX.md) — what is verified at what level
- [docs/MILESTONES.md](docs/MILESTONES.md) — M0–M12 with acceptance tests
- [docs/ARTIFACTS_AND_RETENTION.md](docs/ARTIFACTS_AND_RETENTION.md) — canonical artifacts, caps, retention classes
- [docs/SECURITY.md](docs/SECURITY.md) — security review + known gaps
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — run/demo/migrate/recover/clean-checkout
- [docs/TESTING.md](docs/TESTING.md) — test layers and what is NOT covered
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — setup, quality gates, working rules
- [docs/SAFETY.md](docs/SAFETY.md) — software safety status + M10 hardware checklist
- [docs/LEGACY_KNOWLEDGE_MAP.md](docs/LEGACY_KNOWLEDGE_MAP.md) — what is known/inferred/unknown about the legacy system

## Principles

1. GitHub is the source of truth; a feature is complete only when pushed and verified there.
2. No fake progress: STUB is STUB, SIMULATED is SIMULATED, UNKNOWN is UNKNOWN.
3. Canonical, bounded artifacts — never a file per event.
4. Explicit outcomes everywhere: protocol results, FSM transitions, error envelopes.
5. "Medirover genuinely works" is the definition of done — not file count.
