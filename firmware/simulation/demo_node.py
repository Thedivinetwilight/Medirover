"""Simulated demo node (standalone process).

Usage:
    python -m firmware.simulation.demo_node --ws ws://127.0.0.1:8000/ws/node \
        --node-id motion-01 [--drop-every 30] [--drop-for 4] [--drive-every 15]

SIMULATION ONLY. Periodic simulated link drops demonstrate the
disconnect/reconnect path; the node auto-reconnects deterministically.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from firmware.common.node_context import NodeConfig
from firmware.communication.client import ClientSettings
from firmware.communication.ws_transport import WebSocketNodeTransport
from firmware.hardware.simulated import SimulatedHardware
from firmware.motion_node.node import MotionNode

logger = logging.getLogger("medirover.demo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Medirover simulated demo node")
    p.add_argument("--ws", default="ws://127.0.0.1:8000/ws/node", help="backend node WebSocket URL")
    p.add_argument("--node-id", default="motion-01")
    p.add_argument("--node-name", default="Medirover Motion Node (simulated)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--heartbeat", type=float, default=1.0, help="heartbeat interval seconds")
    p.add_argument("--telemetry", type=float, default=1.0, help="telemetry interval seconds")
    p.add_argument("--drop-every", type=float, default=30.0, help="simulated link drop period (0=off)")
    p.add_argument("--drop-for", type=float, default=4.0, help="simulated link drop duration seconds")
    p.add_argument("--drive-every", type=float, default=15.0, help="demo drive cycle period (0=off)")
    p.add_argument("--drive-duration", type=float, default=3.0)
    return p.parse_args(argv)


async def _drop_loop(
    transport: WebSocketNodeTransport, stop: asyncio.Event, every: float, duration: float
) -> None:
    if every <= 0:
        return
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=every)
        except TimeoutError:
            pass
        if stop.is_set():
            return
        logger.info("SIMULATED LINK DROP for %.1fs (node will reconnect)", duration)
        await transport.close()
        await asyncio.sleep(duration)
        # wait for the client to re-establish the link before the next drop
        for _ in range(100):
            if stop.is_set() or transport.connected:
                break
            await asyncio.sleep(0.1)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    config = NodeConfig(
        node_id=args.node_id,
        node_name=args.node_name,
        node_type="motion",
        capabilities=["demo-drive", "telemetry"],
        seed=args.seed,
        heartbeat_interval_s=args.heartbeat,
        telemetry_interval_s=args.telemetry,
        drive_every_s=args.drive_every,
        drive_duration_s=args.drive_duration,
    )
    hardware = SimulatedHardware(config.node_id, seed=config.seed)
    transport = WebSocketNodeTransport(args.ws)
    node = MotionNode(
        config,
        hardware,
        transport,
        ClientSettings(
            heartbeat_interval_s=args.heartbeat,
            telemetry_interval_s=args.telemetry,
            reconnect_backoff_initial_s=0.5,
            reconnect_backoff_max_s=10.0,
        ),
    )

    stop = asyncio.Event()

    def _signal_stop() -> None:
        logger.info("stop requested")
        stop.set()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_stop)
            except NotImplementedError:  # pragma: no cover (non-unix)
                pass
        drop_task = asyncio.create_task(_drop_loop(transport, stop, args.drop_every, args.drop_for))
        await node.run(stop)
        drop_task.cancel()

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
