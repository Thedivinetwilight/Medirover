"""NodeSupervisor: deterministic timeout handling (master directive §12).

Handles, with explicit and testable behavior:
- heartbeat late          -> ONLINE  -> STALE   (event NODE_STALE)
- heartbeat timeout       -> (STALE|ONLINE) -> OFFLINE (event NODE_OFFLINE)
- identify never arrived  -> connection closed (event IDENTIFY_TIMEOUT)
- event retention prune   -> bounded table
"""

from __future__ import annotations

import asyncio
import logging

from shared.types import ConnectivityEvent as CE
from shared.types import ConnectivityState as CS
from shared.types import Severity
from shared.utils.timeutil import age_seconds, now_utc, parse_iso

logger = logging.getLogger("medirover.supervisor")


class NodeSupervisor:
    def __init__(self, settings, node_manager, eventing) -> None:
        self._settings = settings
        self._manager = node_manager
        self._eventing = eventing
        self._tick = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._tick_once()
            except Exception:  # noqa: BLE001 — supervisor must never die
                logger.exception("supervisor tick failed")
            await asyncio.sleep(self._settings.supervisor_scan_s)

    async def stop(self) -> None:
        self._running = False

    async def _tick_once(self) -> None:
        now = now_utc()
        for node_id in self._manager.node_ids():
            state = self._manager.runtime_state(node_id)
            fsm = self._manager.fsm(node_id)
            if state is None or fsm is None:
                continue
            connectivity = state["connectivity"]
            if connectivity not in (CS.ONLINE.value, CS.STALE.value):
                continue
            last_hb = state.get("last_heartbeat_at")
            if last_hb is None:
                continue
            age = age_seconds(parse_iso(last_hb), now)
            if age > self._settings.offline_after_s:
                if fsm.can(CE.HEARTBEAT_TIMEOUT):
                    fsm.send(CE.HEARTBEAT_TIMEOUT)
                    self._manager.persist_runtime(node_id, connectivity=CS.OFFLINE.value)
                    await self._eventing.record(
                        "NODE_OFFLINE",
                        source="supervisor",
                        node_id=node_id,
                        message=f"no heartbeat for {age:.1f}s (> {self._settings.offline_after_s}s)",
                        severity=Severity.ERROR,
                        state={"connectivity": CS.OFFLINE.value, "age_s": round(age, 1)},
                    )
                    self._manager.broadcast_state(node_id, force=True)
            elif (
                age > self._settings.stale_after_s
                and connectivity == CS.ONLINE.value
                and fsm.can(CE.HEARTBEAT_LATE)
            ):
                fsm.send(CE.HEARTBEAT_LATE)
                self._manager.persist_runtime(node_id, connectivity=CS.STALE.value)
                await self._eventing.record(
                    "NODE_STALE",
                    source="supervisor",
                    node_id=node_id,
                    message=f"heartbeat late by {age - self._settings.heartbeat_interval_s:.1f}s",
                    severity=Severity.WARNING,
                    state={"connectivity": CS.STALE.value, "age_s": round(age, 1)},
                )
                self._manager.broadcast_state(node_id, force=True)

        for conn in self._manager.pending_connections():
            waited = age_seconds(conn.connected_at, now)
            if waited > self._settings.identify_timeout_s:
                self._manager.fail_pending(conn.conn_id, f"identify timeout after {waited:.1f}s")

        self._tick += 1
        if self._tick % max(1, int(60 / self._settings.supervisor_scan_s)) == 0:
            self._eventing.prune()
