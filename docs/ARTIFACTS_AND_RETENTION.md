# Medirover — Artifacts & Retention

The rebuild directive mandates canonical, bounded artifacts (the legacy
~1.1 GB / 13,000+ file incident is the reference failure). Rules:

1. **One canonical artifact per data stream** — never one file per event/run.
2. **Bounded sizes** — every artifact has a cap; caps are enforced in code.
3. **Retention classes** — each artifact is classified; deletion is allowed
   only for CACHE, and never for CRITICAL/HISTORICAL.
4. **Dedup by content hash** — where duplicates can occur (checkpoints,
   manifests), sha256 identifies content.

## Canonical artifacts in this repository

| Path | Class | Cap | Producer |
|---|---|---|---|
| `recovery/PROJECT_STATE.json` | CRITICAL | one compact JSON (atomic tmp+fsync+replace) | `tools/project_state.py` |
| `recovery/PROJECT_STATE.md` | HISTORICAL (rendered) | one file, regenerated from JSON | same (rendered summary, not hand-edited) |
| `recovery/artifact_manifest.json` | HISTORICAL | one file; sha256 per tracked artifact | `tools/artifact_manifest.py build` |
| `results/test_history.jsonl` | HISTORICAL | **500 lines** (oldest dropped) | `tests/conftest.py` sessionfinish |
| `results/storage_audit.json` | CACHE | one file, overwritten per audit | `tools/storage.py audit` |
| `results/persistence_validation.json` | CACHE | one file | `tests/persistence/test_process_boundary.py` |
| `results/clean_checkout_validation.json` | HISTORICAL | one file, overwritten per run | `scripts/clean_checkout.py` |
| `data/*.db*` (SQLite) | CRITICAL (user data) | operational; pruned by retention jobs (events: `EVENT_RETENTION_S`, cap per node) | backend |
| `.venv/`, `__pycache__/`, `*.pyc`, logs | CACHE / EXCLUDED | — | never committed (`.gitignore`) |

## Retention classes

- **CRITICAL** — identity, state, user data. Never auto-deleted.
- **HISTORICAL** — audit trail. Bounded, never auto-deleted below cap.
- **CACHE** — regenerable. May be deleted/overwritten freely.
- **EXCLUDED** — build deps, caches, secrets: never in Git, never artifacts.

## Enforcement

- `tools/storage.py audit` walks the workspace, counts files/bytes, and exits
  0 (OK) / 1 (WARNING) / 2 (CRITICAL) against thresholds
  (`--warn-files/--warn-bytes/--crit-files/--crit-bytes`; CI uses
  warn 5 000 files / 200 MiB, crit 8 000 / 500 MiB and fails only on 2).
- `tests/test_idempotency.py` asserts the audit itself produces exactly one
  bounded file and that repeated state-tool runs never multiply artifacts.
- `tests/test_crash_recovery.py` asserts orphan `.tmp` checkpoint files are
  cleaned and that a crashed write cannot corrupt the canonical state.
- `.gitignore` keeps `.venv`, caches, and `data/` databases out of Git.
  Under `results/` only the four canonical artifacts are tracked
  (`test_history.jsonl`, `storage_audit.json`, `persistence_validation.json`,
  `clean_checkout_validation.json`); anything else `results/*` is ignored.
