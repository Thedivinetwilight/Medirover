"""Start the full simulated demo: backend (API + dashboard) + demo node.

    python scripts/demo.py [--env simulation] [--port 8000]
                           [--drop-every 30] [--drop-for 4] [--drive-every 15]

Steps (clean-checkout friendly):
  1. load environment config (config/<env>.yaml + MEDIROVER_* overrides)
  2. run database migrations (alembic upgrade head) — explicit, never silent
  3. spawn the simulated node as a separate OS process (real process boundary)
  4. start uvicorn (0.0.0.0 so it is reachable through the preview proxy)

Open http://localhost:<port>/ in a browser. The node is labeled SIMULATED.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.config import REPO_ROOT as CFG_ROOT  # noqa: E402
from backend.config import load_environment_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Medirover simulated demo")
    parser.add_argument("--env", default="simulation", choices=["development", "testing", "simulation"])
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--drop-every", type=float, default=None, help="0 disables simulated link drops")
    parser.add_argument("--drop-for", type=float, default=None)
    parser.add_argument("--drive-every", type=float, default=None, help="0 disables the demo drive cycle")
    parser.add_argument("--node-id", default=None)
    args = parser.parse_args()

    settings = load_environment_config(args.env)
    if args.port is not None:
        settings.port = args.port

    # 2. migrations (explicit)
    os.environ["MEDIROVER_DB_URL"] = settings.db_url
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(CFG_ROOT / "alembic.ini"))
    print(f"[demo] migrating database: {settings.db_url}")
    command.upgrade(alembic_cfg, "head")

    # 3. demo node (separate process)
    demo = settings.demo
    node_cmd = [
        sys.executable,
        "-m",
        "firmware.simulation.demo_node",
        "--ws",
        f"ws://127.0.0.1:{settings.port}/ws/node",
        "--node-id",
        args.node_id or demo.node_id,
        "--node-name",
        demo.node_name,
        "--heartbeat",
        str(settings.heartbeat_interval_s),
        "--telemetry",
        str(settings.telemetry_interval_s),
        "--seed",
        str(settings.seed if settings.seed is not None else 42),
        "--drop-every",
        str(args.drop_every if args.drop_every is not None else demo.drop_every_s),
        "--drop-for",
        str(args.drop_for if args.drop_for is not None else demo.drop_for_s),
        "--drive-every",
        str(args.drive_every if args.drive_every is not None else demo.drive_every_s),
        "--drive-duration",
        str(demo.drive_duration_s),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CFG_ROOT)
    print(f"[demo] starting simulated node: {' '.join(node_cmd[2:])}")
    node_proc = subprocess.Popen(node_cmd, cwd=str(CFG_ROOT), env=env)

    # 4. backend
    import uvicorn

    from backend.api.app import create_app

    app = create_app(settings)
    print(f"[demo] backend on http://{settings.host}:{settings.port}/  (env={args.env}, SIMULATED)")
    print("[demo] Ctrl-C to stop")
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    finally:
        node_proc.terminate()
        try:
            node_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            node_proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
