"""Clean-checkout acceptance test (master directive §43, §28).

Verifies a FRESH clone of the repository can, without any hidden workspace
state:

    clone -> venv -> install -> migrate -> test -> start backend
    -> start simulation node -> API + frontend + live state checks

Writes results/clean_checkout_validation.json (canonical, overwritten).

Usage:
    python scripts/clean_checkout.py [--remote] [--keep]
      --remote  clone from the GitHub remote instead of the local repo path
      --keep    keep the temporary clone on failure (default behavior)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "results" / "clean_checkout_validation.json"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(
    cmd: list[str], cwd: Path, env: dict | None = None, timeout: int = 900
) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)


def _wait_http(url: str, timeout_s: float = 30.0) -> bytes:
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.5)
    raise TimeoutError(f"HTTP not ready at {url}: {last_err}")


def _ws_snapshot_check(port: int, timeout_s: float = 20.0) -> dict:
    """Connect to /ws/state, read the snapshot, verify a node is present."""
    import asyncio

    from websockets.asyncio.client import connect

    async def _check() -> dict:
        async with connect(f"ws://127.0.0.1:{port}/ws/state") as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
            import json as _json

            frame = _json.loads(raw)
            return frame

    return asyncio.run(_check())


def main() -> int:
    parser = argparse.ArgumentParser(description="Medirover clean-checkout acceptance test")
    parser.add_argument("--remote", action="store_true", help="clone from GitHub remote")
    args = parser.parse_args()

    steps: list[dict] = []
    tmp = Path(tempfile.mkdtemp(prefix="medirover-cc-"))
    clone = tmp / "repo"
    passed = True
    started = time.time()

    def step(name: str, fn) -> None:
        nonlocal passed
        t0 = time.time()
        try:
            detail = fn() or ""
            steps.append(
                {"name": name, "ok": True, "duration_s": round(time.time() - t0, 2), "detail": detail}
            )
            print(f"  [ok] {name} ({time.time() - t0:.1f}s) {detail}")
        except Exception as exc:  # noqa: BLE001
            passed = False
            steps.append(
                {"name": name, "ok": False, "duration_s": round(time.time() - t0, 2), "detail": str(exc)}
            )
            print(f"  [FAIL] {name}: {exc}")

    print(f"clean-checkout: workspace {tmp}")

    # 1. clone
    def do_clone() -> str:
        if args.remote:
            src = "https://github.com/Thedivinetwilight/Medirover.git"
        else:
            src = str(REPO_ROOT)
        res = _run(["git", "clone", "--quiet", src, str(clone)], cwd=tmp)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-500:])
        commit = _run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()
        return f"src={src} commit={commit[:12]}"

    step("clone", do_clone)

    py = ""

    def do_venv() -> str:
        nonlocal py
        res = _run([sys.executable, "-m", "venv", ".venv"], cwd=clone)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-500:])
        py = str(clone / ".venv" / "bin" / "python")
        res = _run([py, "-m", "pip", "install", "--quiet", "-e", ".[dev]"], cwd=clone, timeout=1200)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout)[-800:])
        return "venv + editable install ok"

    step("install", do_venv)

    db_url = f"sqlite:///{clone / 'data' / 'medirover_cc.db'}"

    def do_migrate() -> str:
        env = dict(os.environ, MEDIROVER_DB_URL=db_url)
        res = _run([py, "-m", "alembic", "upgrade", "head"], cwd=clone, env=env)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout)[-500:])
        return "alembic upgrade head ok"

    step("migrate", do_migrate)

    def do_test() -> str:
        env = dict(os.environ, MEDIROVER_DB_URL=db_url)
        res = _run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=clone, env=env, timeout=1200)
        tail = (res.stdout or res.stderr).strip().splitlines()[-1:]
        if res.returncode != 0:
            raise RuntimeError("tests failed: " + " ".join(tail))
        return " ".join(tail)

    step("pytest", do_test)

    port = _free_port()
    backend_proc = None
    node_proc = None

    def do_start() -> str:
        nonlocal backend_proc, node_proc
        env = dict(
            os.environ,
            MEDIROVER_ENVIRONMENT="simulation",
            MEDIROVER_PORT=str(port),
            MEDIROVER_DB_URL=db_url,
            MEDIROVER_LOG_LEVEL="WARNING",
        )
        (clone / "data").mkdir(exist_ok=True)
        backend_proc = subprocess.Popen(
            [py, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(clone),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_http(f"http://127.0.0.1:{port}/api/v1/health", timeout_s=30)
        except Exception as exc:
            out = backend_proc.stdout.read() if backend_proc.stdout else ""
            raise RuntimeError(f"backend did not start: {out[-500:]}") from exc
        node_proc = subprocess.Popen(
            [
                py,
                "-m",
                "firmware.simulation.demo_node",
                "--ws",
                f"ws://127.0.0.1:{port}/ws/node",
                "--node-id",
                "motion-cc",
                "--drop-every",
                "0",
                "--drive-every",
                "5",
            ],
            cwd=str(clone),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"backend :{port} + node motion-cc"

    step("start backend+node", do_start)

    def do_api() -> str:
        deadline = time.time() + 20
        while time.time() < deadline:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/nodes", timeout=3) as resp:  # noqa: S310
                nodes = json.loads(resp.read())
            for n in nodes:
                if n["node_id"] == "motion-cc" and n["state"]["connectivity"] == "ONLINE":
                    break
            else:
                time.sleep(0.5)
                continue
            break
        else:
            raise RuntimeError("node never reached ONLINE")
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/nodes/motion-cc/telemetry?limit=50", timeout=3
        ) as resp:  # noqa: S310
            telemetry = json.loads(resp.read())
        if not telemetry:
            raise RuntimeError("no telemetry rows")
        return f"ONLINE, {len(telemetry)} telemetry rows"

    step("api: node online + telemetry", do_api)

    def do_frontend() -> str:
        body = _wait_http(f"http://127.0.0.1:{port}/", timeout_s=10).decode()
        if "MEDIROVER" not in body.upper():
            raise RuntimeError("frontend index missing marker")
        return "index served"

    step("frontend served", do_frontend)

    def do_ws() -> str:
        frame = _ws_snapshot_check(port)
        if frame.get("message_type") != "state_snapshot":
            raise RuntimeError(f"expected state_snapshot, got {frame.get('message_type')}")
        node_ids = [n["node_id"] for n in frame["payload"]["nodes"]]
        if "motion-cc" not in node_ids:
            raise RuntimeError("snapshot missing node")
        return "state_snapshot with node"

    step("frontend websocket snapshot", do_ws)

    def do_storage() -> str:
        res = _run([py, "tools/storage.py", "audit"], cwd=clone)
        if res.returncode > 1:
            raise RuntimeError(f"storage verdict > WARNING: {res.stdout.strip()}")
        return res.stdout.strip()

    step("storage audit", do_storage)

    def do_stop() -> str:
        nonlocal backend_proc, node_proc
        for proc in (node_proc, backend_proc):
            if proc is not None:
                proc.terminate()
        for proc in (node_proc, backend_proc):
            if proc is not None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        return "stopped"

    step("stop", do_stop)

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed,
        "mode": "remote" if args.remote else "local-clone",
        "total_duration_s": round(time.time() - started, 1),
        "steps": steps,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nclean-checkout {'PASSED' if passed else 'FAILED'} ({report['total_duration_s']}s)")
    print(f"report: {RESULTS.relative_to(REPO_ROOT)}")
    if passed and not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
