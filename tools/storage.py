"""Storage audit (master directive §3, §42).

Bounded, deterministic, single canonical output (results/storage_audit.json).
Fails the build only at CRITICAL; WARNING is advisory.

CLI:
    python tools/storage.py audit [--repo PATH]
                                  [--warn-files N] [--warn-bytes N]
                                  [--crit-files N] [--crit-bytes N] [--json OUT]
Exit codes: 0 OK, 1 WARNING, 2 CRITICAL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from shared.utils.timeutil import now_utc, to_iso

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
    ".pio",
    ".cache",
    "htmlcov",
    ".tox",
    ".nox",
    ".next",
    ".turbo",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def audit(repo: Path) -> dict:
    total_bytes = 0
    file_count = 0
    dir_bytes: dict[str, int] = {}
    largest_files: list[tuple[str, int]] = []

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for name in files:
            if Path(name).suffix in EXCLUDED_SUFFIXES:
                continue
            path = Path(root) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += size
            rel = str(path.relative_to(repo))
            top = rel.split("/", 1)[0] or "."
            dir_bytes[top] = dir_bytes.get(top, 0) + size
            largest_files.append((rel, size))

    largest_files.sort(key=lambda x: -x[1])
    largest_dirs = sorted(dir_bytes.items(), key=lambda x: -x[1])[:10]
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "largest_dirs": [[k, v] for k, v in largest_dirs],
        "largest_files": largest_files[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Medirover storage audit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--repo", default=".")
    p.add_argument("--warn-files", type=int, default=5000)
    p.add_argument("--warn-bytes", type=int, default=200 * 1024 * 1024)
    p.add_argument("--crit-files", type=int, default=8000)
    p.add_argument("--crit-bytes", type=int, default=500 * 1024 * 1024)
    p.add_argument("--json", default=None, help="output path (default results/storage_audit.json)")
    args = parser.parse_args(p_args(argv))

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: repo path not found: {repo}", file=sys.stderr)
        return 2
    result = audit(repo)
    verdict = "OK"
    if result["file_count"] >= args.crit_files or result["total_bytes"] >= args.crit_bytes:
        verdict = "CRITICAL"
    elif result["file_count"] >= args.warn_files or result["total_bytes"] >= args.warn_bytes:
        verdict = "WARNING"

    report = {
        "ts": to_iso(now_utc()),
        "repo": str(repo),
        "file_count": result["file_count"],
        "total_bytes": result["total_bytes"],
        "largest_dirs": result["largest_dirs"],
        "largest_files": result["largest_files"],
        "thresholds": {
            "warn_files": args.warn_files,
            "warn_bytes": args.warn_bytes,
            "crit_files": args.crit_files,
            "crit_bytes": args.crit_bytes,
        },
        "verdict": verdict,
    }
    out_path = Path(args.json) if args.json else repo / "results" / "storage_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"storage audit: {verdict} — {result['file_count']} files, "
        f"{result['total_bytes'] / (1024 * 1024):.2f} MiB -> {out_path}"
    )
    return {"OK": 0, "WARNING": 1, "CRITICAL": 2}[verdict]


def p_args(argv: list[str] | None) -> list[str] | None:
    # 'audit' is the only subcommand; allow omitting it
    if argv is None:
        return None
    if argv and argv[0] == "audit":
        return argv
    return ["audit", *argv]


if __name__ == "__main__":
    sys.exit(main())
