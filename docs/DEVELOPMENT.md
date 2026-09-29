# Medirover — Development

Environment: Python 3.11 (venv required — PEP 668), Node 22 (frontend logic
tests only; the frontend has **no build step**).

## Setup

```bash
make install     # python3 -m venv .venv && pip install -e ".[dev]"
make check       # ruff check . + mypy + pytest  — must be green before committing
make test-frontend
```

## Quality gates (all must pass before a commit lands)

1. `ruff check .` — line length 110; selects E, F, W, I, B, UP (bugbear
   `extend-immutable-calls` configured for `Depends`/`Query`).
2. `mypy` — strict over backend/firmware/shared/tools/scripts; 0 errors.
3. `pytest` — full suite (unit + integration + e2e) green.
4. `node --test 'frontend/tests/**/*.test.mjs'` green.
5. `tools/storage.py audit` — no storage growth beyond thresholds.
6. **Diff review** — inspect the full diff before pushing (no bulk
   auto-fixes without review).

CI (`.github/workflows/ci.yml`) runs 1–5 on every push/PR; the storage audit
fails the build only at CRITICAL (exit 2).

## Working rules (from the rebuild directive)

- **No fake progress.** A component is labelled by its real status
  (see STATUS_MATRIX.md). "Implemented" ≠ "stubbed"; "verified" ≠ "simulated";
  simulation is never reported as hardware verification. Unknown → UNKNOWN.
- **Focused commits.** One concern per commit, descriptive message; never
  mix generated files, caches, or secrets into a commit.
- **Artifact discipline.** New data streams get a canonical bounded artifact
  (see ARTIFACTS_AND_RETENTION.md) — never per-event files.
- **Shared contracts are law.** Protocol changes happen in `shared/` first
  (schemas + registry + validator + tests); backend and firmware consume
  them. A contract change without known-answer test updates is rejected.
- **Migrations are explicit.** Schema changes ship with an alembic migration
  and the app's `check_migrated` gate continues to refuse unmigrated DBs.
- **Blockers are recorded, then the next highest-value task is taken** —
  with the blocker noted in `recovery/PROJECT_STATE.json`
  (`tools/project_state.py set --json '{"blockers": [...]}')`.

## Where things live (quick map)

| Want to change… | Look in |
|---|---|
| message types / payload shapes | `shared/protocols/registry.py`, `shared/schemas/node.py` |
| validation rules / outcomes | `shared/protocols/validator.py`, `shared/schemas/envelope.py` |
| safety / connectivity rules | `shared/safety/machine.py`, `backend/state/node_fsm.py` |
| node connection handling | `backend/services/node_manager.py` |
| REST surface | `backend/api/routes_*.py` |
| frontend rendering logic | `frontend/js/src/` |
| simulated physics | `firmware/hardware/simulated.py` |
| demo behavior | `scripts/demo.py`, `config/simulation.yaml` |
| timing thresholds | `config/*.yaml` (+ `MEDIROVER_*` env overrides) |
