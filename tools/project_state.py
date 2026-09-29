"""Canonical project state checkpoint (master directive §27, §22, §23).

One machine-readable file (recovery/PROJECT_STATE.json) + one rendered
human summary (recovery/PROJECT_STATE.md). Updated in place, atomically
(temp file + fsync + rename). Never creates per-hour checkpoint copies.

CLI:
    python tools/project_state.py init   --branch X --next-task Y
    python tools/project_state.py set    --json '{"next_task": "..."}'
    python tools/project_state.py validate [--recover]
    python tools/project_state.py show   [--json|--md]

Process boundary: init (process A) -> validate (process B) -> show/set
(process C) is covered by tests/persistence/test_process_boundary.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from shared.schemas.project_state import ProjectState
from shared.utils.timeutil import now_utc, to_iso

REPO_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = REPO_ROOT / "recovery" / "PROJECT_STATE.json"
MD_PATH = REPO_ROOT / "recovery" / "PROJECT_STATE.md"


def json_path() -> Path:
    """Checkpoint JSON location.

    Tests (and sandboxes) can redirect the tool via MEDIROVER_STATE_DIR so
    subprocess-based tests never touch the real recovery/ directory.
    """
    override = os.environ.get("MEDIROVER_STATE_DIR")
    if override:
        return Path(override) / "PROJECT_STATE.json"
    return JSON_PATH


def md_path() -> Path:
    override = os.environ.get("MEDIROVER_STATE_DIR")
    if override:
        return Path(override) / "PROJECT_STATE.md"
    return MD_PATH


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_state() -> ProjectState | None:
    if not json_path().exists():
        return None
    try:
        return ProjectState.model_validate(json.loads(json_path().read_text()))
    except Exception:  # noqa: BLE001
        return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def render_md(state: ProjectState) -> str:
    lines = [
        "# Medirover — Project State",
        "",
        f"_Canonical machine-readable state: `{_display_path(json_path())}`. "
        f"Updated {state.updated_at.isoformat()}. This file is a rendered summary; "
        "do not edit by hand._",
        "",
        f"**Version:** v{state.version}  ",
        f"**Milestone:** current `{state.milestone.current}` | completed "
        f"{', '.join(state.milestone.completed) or '—'} | next "
        f"{state.milestone.next or '—'}",
        "",
        "## Area status",
        "",
        "| area | status |",
        "|---|---|",
    ]
    for area in sorted(state.status):
        lines.append(f"| {area} | {state.status[area].value} |")
    lines += [
        "",
        "## Features",
        "",
        f"- completed: {', '.join(state.features.get('completed', [])) or '—'}",
        f"- active: {state.features.get('active') or '—'}",
        f"- blocked: {', '.join(state.features.get('blocked', [])) or '—'}",
        "",
        "## Known issues",
        "",
    ]
    lines += [f"- {i}" for i in state.known_issues] or ["- none recorded"]
    if state.recovery:
        lines += ["", "## Recovery snapshot", ""]
        for key in sorted(state.recovery):
            value = state.recovery[key]
            if isinstance(value, (list, dict)):
                value = ", ".join(str(v) for v in value) if isinstance(value, list) else json.dumps(value)
            lines.append(f"- **{key}:** {value}")
    ts = state.test_status
    lines += [
        "",
        "## Tests",
        "",
        f"- last run: {ts.last_run.isoformat() if ts.last_run else 'never'} "
        f"({ts.passed} passed / {ts.failed} failed / {ts.errors} errors, {ts.total} total)",
        f"- history: `{ts.history_path}` (canonical, bounded)",
        "",
        "## Hardware / simulation",
        "",
        f"- hardware: {state.hardware_status}",
        f"- simulation: {state.simulation_status}",
        "",
        "## Next task",
        "",
        f"{state.next_task or '—'}",
        "",
        "## Repository",
        "",
        f"- {state.repository.remote} @ {state.repository.branch or '—'}"
        + (f" | last commit `{state.last_commit[:12]}`" if state.last_commit else ""),
        f"- decisions: `{state.decisions_index}`",
        "",
    ]
    return "\n".join(lines)


def write_state(state: ProjectState) -> None:
    atomic_write(json_path(), state.model_dump_json(indent=2) + "\n")
    atomic_write(md_path(), render_md(state))


def cmd_init(args: argparse.Namespace) -> int:
    state = ProjectState.new(branch=args.branch, version=args.version, next_task=args.next_task)
    if args.json:
        overrides = json.loads(args.json)
        data = state.model_dump(mode="json")
        data.update(overrides)
        state = ProjectState.model_validate(data)
    write_state(state)
    print(f"initialized {_display_path(json_path())}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    current = load_state()
    if current is None:
        print("error: no valid PROJECT_STATE.json (run init first)", file=sys.stderr)
        return 1
    data = current.model_dump(mode="json")
    for raw in args.json:
        patch = json.loads(raw)
        if not isinstance(patch, dict):
            print("error: --json must be an object", file=sys.stderr)
            return 1
        data.update(patch)
    data["updated_at"] = to_iso(now_utc())
    state = ProjectState.model_validate(data)
    write_state(state)
    print(f"updated {_display_path(json_path())}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    orphans = list(json_path().parent.glob("*.tmp")) if args.recover else []
    for orphan in orphans:
        orphan.unlink()
        print(f"removed orphan temp file: {orphan.name}")
    if not json_path().exists():
        print("INVALID: PROJECT_STATE.json missing", file=sys.stderr)
        return 1
    state = load_state()
    if state is None:
        print("INVALID: PROJECT_STATE.json failed schema validation", file=sys.stderr)
        return 1
    print(
        f"VALID: milestone={state.milestone.current} version={state.version} "
        f"next_task={state.next_task!r} updated={state.updated_at.isoformat()}"
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    state = load_state()
    if state is None:
        print("error: no valid PROJECT_STATE.json", file=sys.stderr)
        return 1
    if args.json:
        print(state.model_dump_json(indent=2))
    else:
        print(render_md(state))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Medirover project state checkpoint")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--branch", default="")
    p_init.add_argument("--version", default="0.1.0")
    p_init.add_argument("--next-task", default="")
    p_init.add_argument("--json", default=None, help="additional overrides as JSON object")
    p_init.set_defaults(func=cmd_init)

    p_set = sub.add_parser("set")
    p_set.add_argument("--json", action="append", required=True, help="JSON object patch (repeatable)")
    p_set.set_defaults(func=cmd_set)

    p_val = sub.add_parser("validate")
    p_val.add_argument("--recover", action="store_true", help="remove orphan *.tmp files in recovery/")
    p_val.set_defaults(func=cmd_validate)

    p_show = sub.add_parser("show")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
