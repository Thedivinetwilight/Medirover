"""Process boundary: a new process must be able to continue from a checkpoint
written by a previous, already-terminated process (directive §22, §28).

Process A: init -> writes checkpoint -> terminates
Process B: validate -> verifies state -> terminates
Process C: show -> reads state -> continues work (set) -> terminates
Process D: validate again

Each step is a separate OS process (subprocess), exercising exactly the
recovery path a fresh session would use.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY = REPO_ROOT / "recovery"
RESULTS = REPO_ROOT / "results" / "persistence_validation.json"

INIT_JSON = json.dumps(
    {
        "milestone": {"current": "M5", "completed": ["M0", "M1", "M2", "M3", "M4", "M5"], "next": "M6"},
        "last_commit": "process-boundary-test",
        "simulation_status": "RUNNING",
    }
)


def run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/project_state.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_process_boundary_roundtrip():
    steps: list[dict] = []

    # Process A: init (writes checkpoint, then exits)
    ra = run_tool(
        "init",
        "--branch",
        "process-boundary",
        "--next-task",
        "M6: safety command channel",
        "--json",
        INIT_JSON,
    )
    steps.append({"step": "A: init (process)", "ok": ra.returncode == 0, "detail": ra.stdout.strip()})
    assert ra.returncode == 0, ra.stderr
    hash_a = sha256(RECOVERY / "PROJECT_STATE.json")

    # Process B: validate (reads checkpoint from a NEW process)
    rb = run_tool("validate")
    steps.append({"step": "B: validate (new process)", "ok": rb.returncode == 0, "detail": rb.stdout.strip()})
    assert rb.returncode == 0, rb.stderr
    assert "VALID" in rb.stdout
    assert sha256(RECOVERY / "PROJECT_STATE.json") == hash_a  # unchanged by validation

    # Process C: show + continue work (set)
    rc_show = run_tool("show", "--json")
    shown = json.loads(rc_show.stdout)
    assert shown["milestone"]["current"] == "M5"
    assert shown["milestone"]["next"] == "M6"
    assert shown["features"] is not None

    rc_set = run_tool("set", "--json", json.dumps({"next_task": "M6a: e-stop command path"}))
    steps.append(
        {
            "step": "C: show + set (continues work)",
            "ok": rc_show.returncode == 0 and rc_set.returncode == 0,
            "detail": rc_set.stdout.strip(),
        }
    )
    assert rc_set.returncode == 0, rc_set.stderr
    shown2 = json.loads(run_tool("show", "--json").stdout)
    assert shown2["next_task"] == "M6a: e-stop command path"

    # Process D: validate after continued work
    rd = run_tool("validate")
    steps.append(
        {"step": "D: validate (post-continue)", "ok": rd.returncode == 0, "detail": rd.stdout.strip()}
    )
    assert rd.returncode == 0, rd.stderr

    # Canonical artifacts: exactly one checkpoint pair, no temp files
    json_files = list(RECOVERY.glob("PROJECT_STATE.json*"))
    md_files = list(RECOVERY.glob("PROJECT_STATE.md*"))
    tmp_files = list(RECOVERY.glob("*.tmp"))
    assert len(json_files) == 1
    assert len(md_files) == 1
    assert tmp_files == []

    report = {
        "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "valid": True,
        "canonical_file": str((RECOVERY / "PROJECT_STATE.json").relative_to(REPO_ROOT)),
        "sha256_after_A": hash_a,
        "sha256_after_D": sha256(RECOVERY / "PROJECT_STATE.json"),
        "file_count_checkpoint_files": len(json_files) + len(md_files),
        "steps": steps,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
