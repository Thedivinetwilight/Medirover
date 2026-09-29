"""Idempotency: repeating an operation must not explode artifacts (directive §24)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Node, NodeRuntimeState, TelemetryReading
from backend.services.telemetry_ingest import ingest
from shared.schemas.node import TelemetryPayload
from shared.utils.timeutil import now_utc, to_iso

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ingest_twice_same_message_inserts_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/idem.db")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    with sessions() as s:
        s.add(
            Node(
                id="n1",
                name="N",
                node_type="motion",
                firmware_version="0.1.0",
                capabilities=[],
                first_seen_at="t0",
                last_identified_at="t0",
            )
        )
        s.add(
            NodeRuntimeState(
                node_id="n1",
                connectivity="ONLINE",
                safety_state="READY",
                source_kind="SIMULATED",
                last_sequence=0,
                uptime_s=0.0,
                last_telemetry={},
                updated_at="t0",
            )
        )
        s.commit()

    payload = TelemetryPayload(
        tick=1,
        samples=[
            {"sensor_id": "battery_voltage", "value": 12.5, "unit": "V"},
            {"sensor_id": "encoder_left", "value": 100.0, "unit": "ticks"},
        ],
    )
    message_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    with sessions() as s:
        first = ingest(s, "n1", message_id, payload, to_iso(now_utc()))
        second = ingest(s, "n1", message_id, payload, to_iso(now_utc()))
    assert first == 2
    assert second == 0
    with sessions() as s:
        count = len(s.scalars(select(TelemetryReading)).all())
    assert count == 2
    engine.dispose()


def test_project_state_updates_in_place(tmp_path, monkeypatch):
    import tools.project_state as ps

    monkeypatch.setattr(ps, "JSON_PATH", tmp_path / "PROJECT_STATE.json")
    monkeypatch.setattr(ps, "MD_PATH", tmp_path / "PROJECT_STATE.md")

    rc = ps.main(["init", "--branch", "test", "--next-task", "t1"])
    assert rc == 0
    rc = ps.main(["set", "--json", '{"next_task": "t2"}'])
    assert rc == 0
    rc = ps.main(["set", "--json", '{"next_task": "t2"}'])
    assert rc == 0

    files = list(tmp_path.iterdir())
    names = sorted(f.name for f in files)
    assert names == ["PROJECT_STATE.json", "PROJECT_STATE.md"]  # no duplicates, no tmp left


def test_storage_audit_overwrites_single_file(tmp_path):
    """Two audit runs on the same tree -> one canonical output file."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "a.md").write_text("x" * 100)
    (repo / "code.py").write_text("y" * 50)

    out = tmp_path / "results" / "storage_audit.json"
    cmd = [sys.executable, "tools/storage.py", "audit", "--repo", str(repo), "--json", str(out)]
    r1 = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    r2 = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert r1.returncode == 0 and r2.returncode == 0
    assert out.exists()
    assert len(list(tmp_path.glob("results/*.json"))) == 1
    import json

    report = json.loads(out.read_text())
    assert report["file_count"] == 2
    assert report["verdict"] == "OK"


def test_storage_audit_warn_threshold(tmp_path):
    repo = tmp_path / "big"
    repo.mkdir()
    (repo / "blob.bin").write_bytes(b"x" * (600 * 1024 * 1024))  # > warn (500MB default is 500? use explicit)
    out = tmp_path / "storage_audit.json"
    cmd = [
        sys.executable,
        "tools/storage.py",
        "audit",
        "--repo",
        str(repo),
        "--warn-bytes",
        str(100 * 1024 * 1024),
        "--crit-bytes",
        str(1024 * 1024 * 1024),
        "--json",
        str(out),
    ]
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 1  # WARNING


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
