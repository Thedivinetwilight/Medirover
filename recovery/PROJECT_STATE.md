# Medirover — Project State

_Canonical machine-readable state: `recovery/PROJECT_STATE.json`. Updated 2026-09-29T13:49:31.712327+00:00. This file is a rendered summary; do not edit by hand._

**Version:** v0.1.0  
**Milestone:** current `M8` | completed M0, M1, M2, M3, M4, M5, M6, M7 | next M8

## Area status

| area | status |
|---|---|
| architecture | GREEN |
| backend | GREEN |
| communication | GREEN |
| database | GREEN |
| firmware | YELLOW |
| frontend | GREEN |
| hardware | RED |
| reproducibility | GREEN |
| safety | GREEN |
| security | YELLOW |
| simulation | GREEN |
| storage | GREEN |
| testing | GREEN |

## Features

- completed: M0-M6 core rebuild, M5 vertical slice (SIMULATION-VERIFIED), M6 failure/edge/crash/idempotency tests, tooling: project_state/storage/artifact_manifest, docs set (13 files) + README, M7 clean-checkout validation (local-clone run green)
- active: —
- blocked: —

## Known issues

- No auth/TLS — trusted local network only (M12)
- No real hardware — drivers NOT-STARTED (M8-M10)
- Frontend verified via WS payload, not browser rendering

## Recovery snapshot

- **branch:** arena/01a0eafd-medirover
- **build_commands:** make install; make migrate; make demo
- **detected_todos:** none (0 TODO/FIXME); 2 dangling doc refs found and fixed
- **hardware_dependent_areas:** firmware/hardware/simulated.py (placeholder params), config/hardware.yaml (ACK-gated), docs/SAFETY.md M10 checklist
- **incomplete_areas:** real hardware drivers (M8), MCU port (M9), physical integration (M10/M11), auth/TLS (M12), sensor-node e2e coverage
- **languages_frameworks:** Python 3.11 (FastAPI, SQLAlchemy2, alembic, pydantic, websockets); JS ES modules; YAML; Node 22
- **major_subsystems:** [backend api, node manager, ingest, eventing, broadcaster, supervisor, migrations, safety/connectivity FSMs, protocol validator, motion/sensor nodes, simulated hardware, frontend store/ws, demo+clean-checkout scripts, state/storage/manifest tools]
- **repository:** Thedivinetwilight/Medirover
- **snapshot_ts:** 2026-09-29T13:45Z
- **source_tree_summary:** 140 tracked files: backend (FastAPI+SQLAlchemy+alembic), firmware (Python reference nodes + simulated hardware), frontend (no-build ES dashboard), shared (protocol/FSM contracts), config/tools/scripts/tests/docs; 7576 LOC Python
- **starting_commit:** b0dd83f7a16e4c956ccb54b9f6e0dd96f2dfc498
- **test_commands:** make check (ruff+mypy+pytest); make test-frontend; make clean-checkout
- **verification_limitations:** software-only verification (SIMULATION-VERIFIED/UNIT/INTEGRATION); no physical hardware exercised; no headless-browser UI test; legacy codebase contents UNKNOWN

## Tests

- last run: 2026-09-29T03:24:50+00:00 (185 passed / 0 failed / 0 errors, 185 total)
- history: `results/test_history.jsonl` (canonical, bounded)

## Hardware / simulation

- hardware: NO_HARDWARE_ATTACHED
- simulation: SIMULATION-VERIFIED

## Next task

M8: hardware abstraction hardening + real driver skeletons (not started this session)

## Repository

- origin @ arena/01a0eafd-medirover | last commit `e5532a560f0b`
- decisions: `docs/LEGACY_DECISIONS.md`
