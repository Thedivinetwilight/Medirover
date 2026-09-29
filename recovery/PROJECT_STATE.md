# Medirover — Project State

_Canonical machine-readable state: `recovery/PROJECT_STATE.json`. Updated 2026-09-29T14:14:48.194011+00:00. This file is a rendered summary; do not edit by hand._

**Version:** v0.1.0  
**Milestone:** current `M9` | completed M0, M1, M2, M3, M4, M5, M6, M7, M8 | next M9

## Area status

| area | status |
|---|---|
| hardware | YELLOW |

## Features

- completed: M0-M6 core rebuild, M5 vertical slice (SIMULATION-VERIFIED), M6 failure/edge/crash/idempotency tests, tooling: project_state/storage/artifact_manifest, docs set (13 files) + README, M7 clean-checkout validation (local-clone run green), M8: IHardware contract + RealHardware facade (firmware/hardware/real/: DualMotorDriver, EstopLatch, EncoderPair, BatteryMonitor, Board/MemoryBoard), source_kind identify->runtime->DB e2e, 17 fault-injection driver tests + 3 source_kind flow tests + 1 hardware config lock (206 py total)
- active: M9: real MCU firmware port (motion + sensor nodes) against the same protocol
- blocked: —

## Known issues

- No auth/TLS — trusted local network only (M12)
- No physical hardware verification — M8 drivers are fault-injected against MemoryBoard only; MCU port (M9) + physical integration (M10) NOT-STARTED
- Frontend verified via WS payload, not browser rendering
- Sensor node not yet exercised in the e2e vertical slice (coverage gap)

## Recovery snapshot

- **branch:** arena/01a0eafd-medirover
- **build_commands:** make install; make migrate; make demo
- **detected_todos:** none (0 TODO/FIXME)
- **hardware_dependent_areas:** firmware/hardware/real/ (Board port = the M9/M10 boundary), config/hardware.yaml (ACK-gated, drive_every_s=0.0 locked by test), docs/SAFETY.md M10 checklist
- **incomplete_areas:** MCU port (M9), physical integration (M10/M11), auth/TLS (M12), sensor-node e2e coverage
- **languages_frameworks:** Python 3.11 (FastAPI, SQLAlchemy2, alembic, pydantic, websockets); JS ES modules; YAML; Node 22
- **major_subsystems:** backend api, node manager, ingest, eventing, broadcaster, supervisor, migrations, safety/connectivity FSMs, protocol validator, motion/sensor nodes, simulated hardware, real driver skeletons (M8), frontend store/ws, demo+clean-checkout scripts, state/storage/manifest tools
- **repository:** Thedivinetwilight/Medirover
- **snapshot_ts:** 2026-09-29T14:20Z
- **source_tree_summary:** backend (FastAPI+SQLAlchemy+alembic), firmware (reference nodes + simulated hardware + real driver skeletons), frontend (no-build ES dashboard), shared (protocol/FSM contracts), config/tools/scripts/tests/docs; ~8.1k LOC Python
- **starting_commit:** b0dd83f7a16e4c956ccb54b9f6e0dd96f2dfc498
- **test_commands:** make check (ruff+mypy+pytest); make test-frontend; make clean-checkout
- **verification_limitations:** software-only verification (SIMULATION-VERIFIED/UNIT/INTEGRATION); no physical hardware exercised; no headless-browser UI test; legacy codebase contents UNKNOWN

## Tests

- last run: 2026-09-29T14:14:17+00:00 (206 passed / 0 failed / 0 errors, 206 total)
- history: `results/test_history.jsonl` (canonical, bounded)

## Hardware / simulation

- hardware: NO_HARDWARE_ATTACHED
- simulation: SIMULATION-VERIFIED

## Next task

M9 — real MCU firmware port (motion + sensor nodes) with the same shared protocol; acceptance: boot -> identify (source_kind=HARDWARE) -> heartbeat on real node, integration bench. Until then the codebase is stable: make check green (206 py + 4 frontend), boot check green.

## Repository

- origin @ arena/01a0eafd-medirover | last commit `e5532a560f0b`
- decisions: `docs/LEGACY_DECISIONS.md`
