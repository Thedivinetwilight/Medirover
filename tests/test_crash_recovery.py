"""Crash recovery for canonical state + database (directive §23).

Simulated failures: interrupted checkpoint write (orphan temp file),
crashed writer before rename, uncommitted database transaction.
Verified: previous valid state survives, canonical artifacts uncorrupted,
no duplicate artifacts, recovery possible.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_orphan_temp_file_removed_and_state_survives(tmp_path, monkeypatch):
    import tools.project_state as ps
    from shared.schemas.project_state import ProjectState

    monkeypatch.setattr(ps, "JSON_PATH", tmp_path / "PROJECT_STATE.json")
    monkeypatch.setattr(ps, "MD_PATH", tmp_path / "PROJECT_STATE.md")

    state = ProjectState.new(branch="recovery-test", next_task="survive a crash")
    ps.write_state(state)
    hash_before = _sha(ps.JSON_PATH)

    # Simulate an interrupted write: temp file exists, rename never happened
    orphan = tmp_path / "PROJECT_STATE.json.tmp"
    orphan.write_text('{"broken": ')

    rc = ps.main(["validate", "--recover"])
    assert rc == 0
    assert not orphan.exists()
    assert _sha(ps.JSON_PATH) == hash_before  # last valid state untouched
    assert ps.load_state().next_task == "survive a crash"


def test_crashed_writer_before_rename_leaves_valid_state(tmp_path, monkeypatch):
    """Writer 'dies' after writing the temp file but before os.replace()."""
    import tools.project_state as ps
    from shared.schemas.project_state import ProjectState

    monkeypatch.setattr(ps, "JSON_PATH", tmp_path / "PROJECT_STATE.json")
    monkeypatch.setattr(ps, "MD_PATH", tmp_path / "PROJECT_STATE.md")

    good = ProjectState.new(branch="recovery-test", next_task="good state")
    ps.write_state(good)

    # 'Crash': write a partial temp file, stop before the atomic replace
    tmp_file = tmp_path / "PROJECT_STATE.json.tmp"
    tmp_file.write_text('{"schema_version": 1, "updated_at": ')

    # Another session must still see the last valid state
    rc = ps.main(["validate"])
    assert rc == 0
    assert ps.load_state().next_task == "good state"

    # ...and recovery of the temp file works
    rc = ps.main(["validate", "--recover"])
    assert rc == 0
    assert not tmp_file.exists()
    assert ps.load_state().next_task == "good state"


def test_uncommitted_db_transaction_rolls_back_cleanly(tmp_path):
    """A process 'dying' mid-transaction must not corrupt the database."""
    db = tmp_path / "crash.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('committed-row')")
    conn.commit()

    # Begin a transaction, write, then die without committing
    conn.execute("INSERT INTO t (v) VALUES ('uncommitted-row')")
    conn.close()  # rollback on close simulates the crashed process

    conn2 = sqlite3.connect(db)
    integrity = conn2.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    rows = [r[0] for r in conn2.execute("SELECT v FROM t ORDER BY id")]
    assert rows == ["committed-row"]  # previous valid state survives
    conn2.close()


def test_duplicate_checkpoint_files_never_created(tmp_path, monkeypatch):
    import tools.project_state as ps
    from shared.schemas.project_state import ProjectState

    monkeypatch.setattr(ps, "JSON_PATH", tmp_path / "PROJECT_STATE.json")
    monkeypatch.setattr(ps, "MD_PATH", tmp_path / "PROJECT_STATE.md")

    ps.write_state(ProjectState.new(branch="b"))
    ps.write_state(ProjectState.new(branch="b"))
    ps.write_state(ProjectState.new(branch="b"))
    assert len(list(tmp_path.glob("PROJECT_STATE.json*"))) == 1
    assert len(list(tmp_path.glob("*.tmp"))) == 0
