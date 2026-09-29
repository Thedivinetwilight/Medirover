# data/

Runtime data directory. **Everything in here is gitignored** (master
directive §14, §26):

- `medirover_<env>.db` — SQLite databases (development/testing/simulation/hardware),
  created on first use after `alembic upgrade head`.
- WAL/SHM sidecar files.

Rules:

1. Databases are always initialized from migrations on a clean checkout —
   never hand-edited, never committed.
2. Canonical *reference datasets* (if any are ever produced) go here with a
   README entry and are committed via explicit `git add -f` decision, recorded
   in `docs/LEGACY_DECISIONS.md`.
3. Nothing in this directory is a source of truth for code, schemas, or state.
