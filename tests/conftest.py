"""Shared fixtures for cross-cutting tests.

E2E tests run against a REAL uvicorn server + a REAL simulated node over
REAL WebSockets (the same path the browser and demo node use).

Also implements the canonical test history writer (results/test_history.jsonl):
one bounded JSONL line per session, never one file per run (directive §3).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results"
TEST_HISTORY = RESULTS_DIR / "test_history.jsonl"
MAX_HISTORY_LINES = 500


# --------------------------------------------------------------------- history


class _TestHistory:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.total = 0
        self.started = time.time()

    def record(self, report) -> None:
        if report.when != "call" and not (report.when == "setup" and report.failed):
            return
        self.total += 1
        if report.passed:
            self.passed += 1
        elif report.failed:
            self.failed += 1
        else:
            self.errors += 1


_HISTORY = _TestHistory()


def pytest_runtest_logreport(report) -> None:  # noqa: D103
    _HISTORY.record(report)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: D103
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - _HISTORY.started, 1),
        "passed": _HISTORY.passed,
        "failed": _HISTORY.failed,
        "errors": _HISTORY.errors,
        "total": _HISTORY.total,
        "git_commit": commit,
    }
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TEST_HISTORY, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        # bounded history (directive §3)
        lines = TEST_HISTORY.read_text().splitlines()
        if len(lines) > MAX_HISTORY_LINES:
            TEST_HISTORY.write_text("\n".join(lines[-MAX_HISTORY_LINES:]) + "\n")
    except Exception:  # noqa: BLE001 — history writing must never fail the suite
        pass


# --------------------------------------------------------------------- helpers


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_until(predicate, timeout_s: float = 15.0, interval_s: float = 0.05) -> None:
    """Poll a sync-or-async predicate until true or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = predicate()
        if inspect.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(interval_s)
    raise TimeoutError("condition not met in time")


@dataclass
class ServerInfo:
    base_url: str
    port: int
    app: object


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def test_settings(tmp_path):
    from backend.config import Settings

    return Settings(
        environment="testing",
        db_url=f"sqlite:///{tmp_path}/test.db",
        heartbeat_interval_s=0.2,
        telemetry_interval_s=0.1,
        stale_after_s=0.6,
        offline_after_s=1.2,
        supervisor_scan_s=0.05,
        identify_timeout_s=2.0,
        max_frame_bytes=16384,
        frontend_dir=str(REPO_ROOT / "frontend"),
        log_level="WARNING",
        log_json=False,
        seed=1234,
    )


@pytest.fixture
def migrated_db(test_settings):
    """Run alembic migrations on a fresh isolated test database."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    os.environ["MEDIROVER_DB_URL"] = test_settings.db_url
    try:
        cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("MEDIROVER_DB_URL", None)
    return test_settings.db_url


@pytest.fixture
async def server(migrated_db, test_settings):
    """Real uvicorn server on an ephemeral port (real transport path)."""
    import uvicorn

    from backend.api.app import create_app

    app = create_app(test_settings)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uv_server = uvicorn.Server(config)
    task = asyncio.create_task(uv_server.serve())
    try:
        deadline = time.monotonic() + 20
        while not uv_server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn did not start")
            await asyncio.sleep(0.05)
        import httpx

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as probe:
            for _ in range(100):
                try:
                    if (await probe.get("/api/v1/health")).status_code == 200:
                        break
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(0.1)
        yield ServerInfo(base_url=f"http://127.0.0.1:{port}", port=port, app=app)
    finally:
        uv_server.should_exit = True
        await task


@pytest.fixture
async def api_client(server):
    import httpx

    async with httpx.AsyncClient(base_url=server.base_url, timeout=5.0) as client:
        yield client


@pytest.fixture
def node_factory(server, test_settings):
    """Builds a MotionNode wired to the live server via a real WebSocket."""
    from firmware.common.node_context import NodeConfig
    from firmware.communication.client import ClientSettings
    from firmware.communication.ws_transport import WebSocketNodeTransport
    from firmware.hardware.simulated import SimulatedHardware
    from firmware.motion_node.node import MotionNode

    def _make(node_id: str = "motion-e2e", **config_overrides) -> MotionNode:
        config = NodeConfig(
            node_id=node_id,
            node_name=f"E2E Node {node_id}",
            node_type="motion",
            capabilities=["demo-drive", "telemetry"],
            seed=99,
            heartbeat_interval_s=test_settings.heartbeat_interval_s,
            telemetry_interval_s=test_settings.telemetry_interval_s,
            drive_every_s=0,  # deterministic: no self-issued drives in tests
            **config_overrides,
        )
        hw = SimulatedHardware(node_id, seed=config.seed)
        transport = WebSocketNodeTransport(f"ws://127.0.0.1:{server.port}/ws/node")
        return MotionNode(
            config,
            hw,
            transport,
            ClientSettings(
                heartbeat_interval_s=test_settings.heartbeat_interval_s,
                telemetry_interval_s=test_settings.telemetry_interval_s,
                welcome_timeout_s=3.0,
                reconnect_backoff_initial_s=0.1,
                reconnect_backoff_max_s=0.5,
            ),
        )

    return _make


@pytest.fixture
async def node(server, node_factory):
    """One live node attached to the server, running as a task."""
    import asyncio as _asyncio

    n = node_factory()
    stop = _asyncio.Event()
    task = _asyncio.create_task(n.run(stop))
    yield n
    n.stop()
    await task
