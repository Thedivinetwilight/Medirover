# Medirover — Operations

Status: procedures for the current build (simulation + development).
Hardware operation is NOT-STARTED (M10) — see [SAFETY.md](SAFETY.md).

## 1. Run the demo (simulated node + dashboard)

```bash
make install                # venv + editable install (once)
make migrate                # alembic upgrade head on the default (development) DB
make demo                   # = .venv/bin/python scripts/demo.py
```

`scripts/demo.py` (default `--env simulation`, port 8000):
sets `MEDIROVER_DB_URL` from the chosen profile, runs `alembic upgrade head`,
starts a demo node in a **subprocess** (`firmware/simulation/demo_node.py`,
node id `motion-01`, simulated hardware), then starts uvicorn with the
backend. Open `http://<host>:8000/` — the dashboard shows the node going
ONLINE with live telemetry, an event feed, and (every 15 s by default) a
drive cycle. The simulation profile also simulates a 4 s link drop every
30 s so you can watch OFFLINE → recovery live.

Useful flags: `--env development|testing|simulation`, `--port N`,
`--drop-every S` (`0` disables drops), `--drop-for S`, `--drive-every S`
(`0` disables the drive cycle), `--node-id ID`.

Stop with Ctrl-C — the node subprocess and server shut down cleanly (node
close is a clean WS close → OFFLINE + `NODE_DISCONNECTED` event).

## 2. Environment profiles (`config/`)

| Profile | Host:port | DB | hb / stale / offline | Purpose |
|---|---|---|---|---|
| `testing.yaml` | 127.0.0.1:8010 | `data/medirover_test.db` | 0.2 / 0.6 / 1.2 s | fast suite timings |
| `development.yaml` | 0.0.0.0:8000 | `data/medirover_dev.db` | 1.0 / 3.0 / 10.0 s | local dev |
| `simulation.yaml` | 0.0.0.0:8000 | `data/medirover_sim.db` | 1.0 / 3.0 / 10.0 s | demo dashboard (drops + drive) |
| `hardware.yaml` | 0.0.0.0:8000 | `data/medirover_hardware.db` | (placeholders) | **requires `MEDIROVER_HARDWARE_ACK=yes`**; M10 |

Overrides: any setting can be set via `MEDIROVER_<SETTING>` environment
variables (e.g. `MEDIROVER_PORT=9000`, `MEDIROVER_DB_URL=sqlite:////tmp/x.db`).
Relative SQLite paths are resolved against the repository root
(`sqlite:///data/x.db` = repo-relative; `sqlite:////abs/x.db` = absolute).

## 3. Database & migrations

- Engine: SQLite, WAL mode. The backend **never auto-migrates**; it refuses
  to start when `alembic current != head` (`check_migrated`).
- Migrate: `make migrate` (or `MEDIROVER_DB_URL=... .venv/bin/python -m
  alembic upgrade head`).
- Tables: `nodes, node_runtime_state, telemetry_readings, events, faults,
  audit` (see `backend/database/models.py`; migration `0001_initial`).
- Databases live in `data/` and are gitignored. Deleting a DB deletes the
  node registry/history — that is destructive, there is no backup mechanism
  in this build (note for M11).

## 4. Checkpoints & recovery

- `tools/project_state.py init|set --json '{...}'|validate [--recover]|show [--json]`
  maintains the canonical compact checkpoint `recovery/PROJECT_STATE.json`
  (atomic tmp+fsync+replace) and a rendered `recovery/PROJECT_STATE.md`.
- `validate --recover` removes orphan `recovery/*.tmp` files left by a
  crashed writer and verifies the JSON.
- `tools/artifact_manifest.py build` → `recovery/artifact_manifest.json`
  (sha256 per tracked artifact).
- After any crash: run `project_state.py validate --recover`, then
  `make migrate && pytest` — SQLite rolls back uncommitted writes; telemetry
  ingestion is idempotent, so reconnect/replay is safe.

## 5. Clean-checkout validation

```bash
make clean-checkout          # local: validates this checkout end-to-end
# or: .venv/bin/python scripts/clean_checkout.py --remote   (clone from GitHub)
```

Clones (or uses) the repo, builds a venv, installs, migrates, runs the full
test suite, boots the backend + a simulated node, asserts ONLINE + telemetry
flow + frontend served + WS snapshot, runs the storage audit, and writes
`results/clean_checkout_validation.json` (exit 0 on success). This is the
directive's acceptance test that the project works from a fresh checkout.
