"""Artifact manifest (master directive §25, §26, §45).

Builds recovery/artifact_manifest.json: a compact, deterministic list of
canonical artifacts with size, sha256, retention class, and provenance.
One canonical file, updated in place — never a copy per run.

Retention classes (directive §26):
  CRITICAL       unique, non-regenerable (source, tests, migrations, recovery)
  IMPORTANT      docs, config, canonical results
  REGENERABLE    deterministic build outputs (not listed here by default)

CLI:
    python tools/artifact_manifest.py build [--repo PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from shared.utils.timeutil import now_utc, to_iso

REPO_ROOT = Path(__file__).resolve().parents[1]

#: (glob, retention class, artifact type)
MANIFEST_GLOBS: list[tuple[str, str, str]] = [
    ("README.md", "IMPORTANT", "doc"),
    ("Makefile", "IMPORTANT", "tooling"),
    ("alembic.ini", "CRITICAL", "tooling"),
    ("pyproject.toml", "CRITICAL", "tooling"),
    (".github/workflows/*.yml", "IMPORTANT", "tooling"),
    ("docs/*.md", "IMPORTANT", "doc"),
    ("recovery/PROJECT_STATE.json", "CRITICAL", "state"),
    ("recovery/PROJECT_STATE.md", "CRITICAL", "state"),
    ("recovery/legacy_reference_manifest.json", "CRITICAL", "state"),
    ("config/*.yaml", "IMPORTANT", "config"),
    ("shared/**/*.py", "CRITICAL", "source"),
    ("backend/**/*.py", "CRITICAL", "source"),
    ("backend/database/migrations/versions/*.py", "CRITICAL", "migration"),
    ("firmware/**/*.py", "CRITICAL", "firmware"),
    ("frontend/index.html", "CRITICAL", "frontend"),
    ("frontend/**/*.css", "CRITICAL", "frontend"),
    ("frontend/**/*.js", "CRITICAL", "frontend"),
    ("frontend/tests/*.mjs", "IMPORTANT", "test"),
    ("scripts/*.py", "IMPORTANT", "tooling"),
    ("tools/*.py", "IMPORTANT", "tooling"),
    ("tests/**/*.py", "CRITICAL", "test"),
    ("backend/tests/*.py", "CRITICAL", "test"),
    ("firmware/tests/*.py", "CRITICAL", "test"),
    ("results/*.jsonl", "IMPORTANT", "canonical_result"),
    ("results/*.json", "IMPORTANT", "canonical_result"),
]

EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "build", "dist"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build(repo: Path) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for pattern, art_class, art_type in MANIFEST_GLOBS:
        for path in sorted(repo.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(repo))
            if rel in seen:
                continue
            seen.add(rel)
            if any(part in EXCLUDED_DIRS for part in path.relative_to(repo).parts[:-1]):
                continue
            entries.append(
                {
                    "path": rel,
                    "type": art_type,
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "class": art_class,
                    "producer": "medirover",
                    "version": "0.1.0",
                    "retention": art_class,
                }
            )
    entries.sort(key=lambda e: e["path"])
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Medirover artifact manifest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--repo", default=".")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    entries = build(repo)
    manifest = {
        "schema_version": 1,
        "generated_at": to_iso(now_utc()),
        "repo": str(repo),
        "entry_count": len(entries),
        "entries": entries,
    }
    out = repo / "recovery" / "artifact_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"artifact manifest: {len(entries)} canonical artifacts -> {out.relative_to(repo)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
