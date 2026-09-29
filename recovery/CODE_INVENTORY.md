# Medirover — Code Inventory

Recovery snapshot. Generated 2026-09-29 against the canonical repository
state. Source of truth: the git tree at the recorded commit, not prior
documentation.

## Repository

- Remote: `https://github.com/Thedivinetwilight/Medirover.git`
- Branch (session/canonical work): `arena/01a0eafd-medirover`
- `main`: `d8a9da9` — legacy "Initial commit" (contains only `.gitignore`;
  the old Medirover codebase is **not** present on `main`)
- Snapshot commit: **b0dd83f** (13 commits above legacy initial)
- Working tree at snapshot: clean (tree hash verified identical to commit)

### Recovery note (2026-09-29)

The workspace arrived with the local branch ref rolled back to `d8a9da9`
while the on-disk content still matched the remote branch. Verified the
working-tree tree hash was byte-identical to `b0dd83f^{tree}` and restored
the branch ref to `b0dd83f`. No content was lost or rewritten. `.venv` had
been wiped; rebuilt via `make install` (environment issue, not a code
defect).

## Languages & frameworks

| Language | Files | Role |
|---|---|---|
| Python 3.11 | 99 (≈7 600 LOC) | backend, firmware, shared contracts, tools, tests |
| JavaScript (ES modules, no build) | 6 | frontend dashboard |
| CSS | 1 | dashboard styling |
| YAML | 4 + CI | environment profiles, GitHub Actions |
| TOML | 1 | pyproject (deps, ruff, mypy, pytest config) |

Frameworks: FastAPI, SQLAlchemy 2, alembic, uvicorn, pydantic v2, websockets
(>=13,<16); Node 22 (`node --test` for frontend logic only).

## Test & build commands (the repository's own)

| Command | What it does |
|---|---|
| `make install` | venv + `pip install -e ".[dev]"` |
| `make check` | ruff + mypy + full pytest |
| `make test-frontend` | `node --test 'frontend/tests/**/*.test.mjs'` |
| `make migrate` | alembic upgrade head (explicit; app never auto-migrates) |
| `make demo` | backend + simulated node subprocess (simulation profile) |
| `make clean-checkout` | full from-clone validation → `results/clean_checkout_validation.json` |
| `make storage-audit` / `make manifest` | bounded-storage audit / artifact manifest |

Baseline at snapshot commit (recorded in `recovery/test_history.jsonl`):
ruff PASS, mypy PASS (86 files), pytest **185 passed**, frontend **4
passed**, backend boot + health + node ONLINE + telemetry PASS.

## Repository structure (real)

```
backend/
  api/         FastAPI app factory, AppContext, REST routes (nodes, telemetry,
               events, faults, health), WS routes (/ws/node, /ws/state),
               error envelope (code/category/severity/recoverable/...)
  core/        structured logging config
  config.py    Settings (pydantic), environment profiles, env-var overrides,
               relative-DB normalization
  database/    models (nodes, node_runtime_state, telemetry_readings, events,
               faults, audit), engine (WAL), migrations/ (alembic, 0001_initial)
  services/    node_manager (identify/heartbeat/telemetry/reject/malformed
               circuit breaker), telemetry_ingest (idempotent upsert),
               eventing (retention pruning), broadcaster (WS fan-out),
               node_supervisor (stale/offline backstop), ws_types (Protocols)
  state/       node_fsm — connectivity FSM table (verbatim in docs)
  tests/       backend unit/integration tests
config/        testing.yaml, development.yaml, simulation.yaml,
               hardware.yaml (requires MEDIROVER_HARDWARE_ACK=yes)
data/          runtime SQLite (gitignored; README only tracked)
docs/          13 docs: ARCHITECTURE, PROTOCOL, STATE_MACHINES, API,
               STATUS_MATRIX, MILESTONES, ARTIFACTS_AND_RETENTION, SECURITY,
               OPERATIONS, TESTING, DEVELOPMENT, SAFETY, LEGACY_KNOWLEDGE_MAP
firmware/
  common/      node_context (NodeConfig)
  communication/ client (NodeProtocolClient: identify-once, sequence,
               reconnect/backoff), ws_transport, simulated_transport (MemoryLink)
  hardware/    interfaces.py (ISensor, IMotorController, IPowerMonitor,
               ISafetyInput, IStatusOutput, IStorage, ICommunication),
               simulated.py (SimulatedHardware — seeded deterministic physics)
  motion_node/ MotionNode — safety FSM owner, heartbeat/telemetry producers,
               E-stop + demo drive handling
  sensor_node/ SensorNode
  simulation/  demo_node.py (subprocess entry for scripts/demo.py)
  tests/       firmware unit tests + fake_backend (in-process protocol peer)
frontend/      index.html, css/, js/src/{state/store.js, services/api.js,
               services/ws_client.js, main.js, components/{status_card,
               event_feed}.js}, tests/store.test.mjs
recovery/      PROJECT_STATE.json/.md (canonical checkpoint),
               artifact_manifest.json, this inventory, ARCHITECTURE.md,
               test_history.jsonl
results/       test_history.jsonl (suite sessions), storage_audit.json,
               persistence_validation.json, clean_checkout_validation.json
scripts/       demo.py, clean_checkout.py
shared/        constants, errors, events, fsm (generic engine), safety
               (safety FSM table), protocols (envelope, codec, registry,
               validator, sequence), schemas (node payloads, envelope,
               project_state), types (all enums StrEnum), utils
               (ids, timeutil, asyncutil)
tests/         cross-cutting: e2e vertical slice, disconnect/reconnect,
               failure injection, idempotency, crash recovery, API contract,
               protocol known-answer, FSM exhaustive, persistence/
tools/         project_state.py, storage.py, artifact_manifest.py (CLIs)
```

## Marker scan (actual grep results at snapshot)

- `TODO` / `FIXME` / `XXX` / `HACK`: **none** in .py/.js/.md
- `raise NotImplementedError`: none (one `except NotImplementedError` guard
  for non-Unix in `firmware/simulation/demo_node.py` — legitimate)
- Self-declared placeholders: `firmware/hardware/simulated.py` — physical
  parameters (e.g. `WHEEL_RADIUS_M = 0.05`) are explicitly marked
  "placeholder assumption (UNKNOWN real hardware)"
- Dead/duplicate code: none detected (single implementation per concern;
  `firmware/tests/fake_backend.py` is a test double at the protocol
  boundary, not a duplicate of the backend)
- Dangling references found (defects, to fix):
  1. `firmware/hardware/simulated.py` docstring cites `docs/HARDWARE.md` —
     file does not exist
  2. `shared/schemas/project_state.py` default `decisions_index` points to
     `docs/LEGACY_DECISIONS.md` — file does not exist (real file:
     `docs/LEGACY_KNOWLEDGE_MAP.md`)

## Historical baseline verification (Phase 4)

The takeover directive cites a historical baseline (269/269 tests, two
ESP32 firmware projects compiling, simulation BOOT→SELF_TEST→IDLE, specific
hardware list: RPi 4, ESP32/NodeMCU, L298, MAX3010x, ECG/EMG/EEG modules,
PCA9685, 12 V lead-acid + Li-ion batteries, encoders, camera, ultrasonic/
PIR/Bluetooth boards). **Verified against this repository:**

| Historical claim | In this repository? | Classification |
|---|---|---|
| 269/269 Python tests | No — suite is 185 tests (different codebase) | NOT PRESENT |
| Two ESP32 firmware projects | No — no C/ESP-IDF/Arduino code anywhere; firmware is a Python reference implementation | NOT PRESENT |
| Simulation boot BOOT→SELF_TEST→IDLE | No — startup model is SAFE→(INIT_OK)→READY on a per-node safety FSM | NOT PRESENT |
| Named hardware (RPi 4, ESP32, L298, MAX3010x, ECG/EMG/EEG, PCA9685, batteries, ...) | No hardware model is recorded anywhere in the repo | NOT VERIFIABLE — hardware identities remain UNKNOWN per the directive's own rule |

Conclusion: the cited historical work belongs to the **legacy** Medirover
codebase, which is **not in this GitHub repository** (main = a single
`.gitignore` commit; the legacy ZIP was never delivered to any workspace).
Nothing from that baseline can be carried forward as fact; per the
standing rules it is classified UNKNOWN/INFERRED in
`docs/LEGACY_KNOWLEDGE_MAP.md`. The current repository is the clean rebuild
branch, and this inventory describes only what exists in it.

## Incomplete areas (actual, from code + milestone docs)

- Real hardware drivers: `firmware/hardware/` ships **interfaces +
  simulated implementation only** — no real motor/encoder/E-stop/battery
  drivers exist yet (milestone M8).
- MCU firmware port (ESP32 etc.): NOT STARTED (M9).
- Physical integration, field operation: NOT STARTED (M10/M11).
- Auth/TLS: NOT STARTED (M12; trusted-local-network assumption documented
  in `docs/SECURITY.md`).
- Navigation / perception / AI-ML: **absent from this codebase** — the
  motion node performs a scripted demo drive cycle and responds to safety
  events; there is no navigation, camera, or computer-vision code. Any such
  capability would be new work, not recovery.
- `sensor_node` exists and is unit-tested but is not exercised by the e2e
  vertical slice (motion node only).

## Hardware-dependent areas

- `firmware/hardware/simulated.py` (physics constants, placeholder-labeled)
- `config/hardware.yaml` (profile exists, requires explicit env ACK; timing
  values are placeholders)
- `docs/SAFETY.md` (M10 hardware checklist — hardwired E-stop, current
  limiting, containment, battery switch, fail-safe direction)
- Nothing in the repository assumes a specific real board; all hardware
  access goes through the `firmware/hardware/interfaces.py` contracts.

## Known verification limitations

- All verification is SIMULATION-VERIFIED or UNIT/INTEGRATION-TESTED at the
  software level. No physical actuator, sensor, E-stop, camera, or battery
  has been exercised. `source_kind=SIMULATED` is reported on every node
  state and the dashboard displays it.
- Frontend is verified via the WS payload contract + `node --test` logic;
  no headless-browser render test exists.
- Legacy codebase contents: UNKNOWN (never available in any workspace).
