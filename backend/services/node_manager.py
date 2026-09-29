"""NodeManager: owns connections, per-node connectivity FSM, runtime state.

This is the single owner of node runtime state (master directive §7:
explicit state ownership). The WebSocket handlers are thin: they hand raw
frames here and send whatever frames come back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings
from backend.database.models import Node, NodeRuntimeState
from backend.services.audit import record_audit
from backend.services.telemetry_ingest import ingest
from backend.services.ws_types import WebSocketLike
from backend.state.node_fsm import make_connectivity_fsm
from shared.constants import MESSAGE_VERSION, PROTOCOL_VERSION
from shared.fsm import StateMachine
from shared.protocols.codec import encode_frame
from shared.protocols.registry import NodeMessageType, ServerMessageType
from shared.protocols.sequence import SequenceTracker
from shared.protocols.validator import FrameValidator
from shared.schemas.envelope import Envelope, ValidationResult
from shared.schemas.node import (
    AckPayload,
    HeartbeatPayload,
    IdentifyPayload,
    RejectPayload,
    TelemetryPayload,
    WelcomePayload,
)
from shared.types import (
    ConnectivityEvent as CE,
)
from shared.types import ConnectivityState as CS
from shared.types import MessageDirection, SafetyState, Severity, SourceKind
from shared.types import ValidationOutcome as VO
from shared.utils.asyncutil import schedule
from shared.utils.ids import new_connection_id, new_message_id
from shared.utils.timeutil import now_utc, to_iso

logger = logging.getLogger("medirover.nodes")

MAX_CONNECTIONS = 32
MALFORMED_LIMIT = 3


@dataclass
class ConnectionContext:
    conn_id: str
    ws: WebSocketLike
    seq: SequenceTracker = field(default_factory=SequenceTracker)
    identified: bool = False
    node_id: str | None = None
    connected_at: datetime = field(default_factory=now_utc)
    last_heartbeat_at: datetime | None = None
    last_message_at: datetime | None = None
    safety_state: SafetyState = SafetyState.SAFE
    uptime_s: float = 0.0
    battery_voltage: float | None = None
    last_telemetry: dict = field(default_factory=dict)
    consecutive_malformed: int = 0


class NodeManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        eventing,
        broadcaster,
    ) -> None:
        self._settings = settings
        self._sessions = session_factory
        self._eventing = eventing
        self._broadcaster = broadcaster
        self._connections: dict[str, ConnectionContext] = {}
        self._node_fsm: dict[str, StateMachine] = {}
        self._runtime: dict[str, dict] = {}
        self._validator = FrameValidator(MessageDirection.NODE_TO_BACKEND)
        self._throttle_map: dict[str, datetime] = {}
        self._last_broadcast: dict[str, datetime] = {}

    # ------------------------------------------------------------------ setup

    def initialize_from_db(self) -> None:
        """Load registered nodes; connectivity resets to DISCONNECTED on restart."""
        with self._sessions() as session:
            nodes = session.scalars(select(Node)).all()
            for node in nodes:
                self._node_fsm[node.id] = make_connectivity_fsm(CS.DISCONNECTED)
                row = session.get(NodeRuntimeState, node.id)
                self._runtime[node.id] = {
                    "node_id": node.id,
                    "connectivity": CS.DISCONNECTED.value,
                    "safety_state": row.safety_state if row else SafetyState.SAFE.value,
                    "source_kind": row.source_kind if row else SourceKind.SIMULATED.value,
                    "last_heartbeat_at": row.last_heartbeat_at if row else None,
                    "last_message_at": row.last_message_at if row else None,
                    "last_sequence": row.last_sequence if row else 0,
                    "battery_voltage": row.battery_voltage if row else None,
                    "uptime_s": row.uptime_s if row else 0.0,
                    "last_telemetry": row.last_telemetry if row else {},
                    "updated_at": row.updated_at if row else None,
                }
        logger.info("initialized %d registered node(s) from database", len(nodes))

    # ------------------------------------------------------------- connections

    def register_connection(self, ws: WebSocketLike) -> ConnectionContext | None:
        if len(self._connections) >= MAX_CONNECTIONS:
            return None
        conn = ConnectionContext(conn_id=new_connection_id(), ws=ws)
        self._connections[conn.conn_id] = conn
        logger.info("node connection opened", extra={"conn_id": conn.conn_id})
        return conn

    def pending_connections(self) -> list[ConnectionContext]:
        return [c for c in self._connections.values() if not c.identified]

    def fail_pending(self, conn_id: str, reason: str) -> None:
        conn = self._connections.pop(conn_id, None)
        if conn is None or conn.identified:
            return
        self._eventing.record_sync(
            "IDENTIFY_TIMEOUT",
            source=conn.conn_id,
            message=f"connection dropped: {reason}",
            severity=Severity.WARNING,
        )
        schedule(conn.ws.close(code=1008))
        logger.warning("pending connection closed: %s", reason, extra={"conn_id": conn_id})

    def on_disconnect(self, conn_id: str) -> None:
        conn = self._connections.pop(conn_id, None)
        if conn is None:
            return
        if not conn.identified or conn.node_id is None:
            logger.info("pending connection closed", extra={"conn_id": conn_id})
            return
        node_id = conn.node_id
        fsm = self._node_fsm.get(node_id)
        new_connectivity = self._runtime[node_id]["connectivity"]
        if fsm is not None and fsm.can(CE.WS_CLOSED):
            new_state = fsm.send(CE.WS_CLOSED)
            new_connectivity = new_state.value
            severity = Severity.WARNING if new_state == CS.OFFLINE else Severity.INFO
            self._eventing.record_sync(
                "NODE_DISCONNECTED",
                source=conn.conn_id,
                node_id=node_id,
                message=f"connection closed; node -> {new_state.value}",
                severity=severity,
                state={"connectivity": new_state.value, "safety_state": conn.safety_state.value},
            )
        else:
            self._eventing.record_sync(
                "NODE_DISCONNECTED",
                source=conn.conn_id,
                node_id=node_id,
                message="connection closed",
                severity=Severity.INFO,
                state={"connectivity": new_connectivity},
            )
        # Persist the FSM-derived state, not the stale runtime value, and
        # broadcast it so the UI transitions immediately (not on next tick).
        self.persist_runtime(node_id, connectivity=new_connectivity)
        self.broadcast_state(node_id, force=True)

    # ------------------------------------------------------------------- frames

    async def handle(self, conn_id: str, raw: str) -> tuple[list[str], bool]:
        """Process one raw frame. Returns (frames_to_send, close_connection)."""
        conn = self._connections.get(conn_id)
        if conn is None:
            return [], True

        if len(raw.encode("utf-8")) > self._settings.max_frame_bytes:
            await self._reject(conn, None, "PROTOCOL_MALFORMED", "frame exceeds size limit")
            self._bump_malformed(conn)
            return await self._malformed_response(conn)

        result = self._validator.validate(raw)
        if not result.is_valid:
            await self._on_invalid(conn, result)
            return await self._malformed_response(conn)

        env = result.envelope
        assert env is not None

        order = conn.seq.check(env.message_id, env.sequence)
        if order == VO.DUPLICATE:
            await self._reject(
                conn, env, "PROTOCOL_DUPLICATE", "duplicate message_id", severity=Severity.DEBUG
            )
            return [], False
        if order == VO.OUT_OF_ORDER:
            await self._reject(
                conn,
                env,
                "PROTOCOL_OUT_OF_ORDER",
                f"sequence {env.sequence} <= last {conn.seq.last_sequence}",
            )
            return [], False

        conn.seq.record(env.message_id, env.sequence)
        conn.last_message_at = now_utc()
        conn.consecutive_malformed = 0

        if env.message_type == NodeMessageType.IDENTIFY.value:
            return await self._handle_identify(conn, env)
        if not conn.identified or conn.node_id is None:
            await self._reject(conn, env, "PROTOCOL_INVALID", "identify before other messages")
            return [], True
        if env.message_type == NodeMessageType.HEARTBEAT.value:
            return await self._handle_heartbeat(conn, env)
        if env.message_type == NodeMessageType.TELEMETRY.value:
            return await self._handle_telemetry(conn, env)
        if env.message_type == NodeMessageType.ACK.value:
            return await self._handle_ack(conn, env)
        return [], False  # validated but unhandled type (should not happen)

    # --------------------------------------------------------------- dispatch

    async def _handle_identify(self, conn: ConnectionContext, env: Envelope) -> tuple[list[str], bool]:
        if conn.identified:
            await self._reject(conn, env, "PROTOCOL_INVALID", "already identified on this connection")
            return [], True
        ip = IdentifyPayload.model_validate(env.payload)
        if ip.node_id != env.node_id:
            await self._reject(conn, env, "PROTOCOL_INVALID", "envelope node_id != payload node_id")
            return [], False
        for other in self._connections.values():
            if other is not conn and other.identified and other.node_id == ip.node_id:
                await self._reject(
                    conn, env, "COMMUNICATION_REJECTED", "node already has an active connection"
                )
                return [], True

        self._upsert_node(ip)
        conn.identified = True
        conn.node_id = ip.node_id
        now = now_utc()
        conn.last_heartbeat_at = now
        conn.last_message_at = now

        fsm = self._node_fsm.setdefault(ip.node_id, make_connectivity_fsm())
        if fsm.can(CE.WS_CONNECTED):
            fsm.send(CE.WS_CONNECTED)
        if fsm.can(CE.IDENTIFY_OK):
            fsm.send(CE.IDENTIFY_OK)

        self.persist_runtime(
            ip.node_id,
            connectivity=CS.ONLINE.value,
            safety_state=conn.safety_state.value,
            source_kind=ip.source_kind.value,
            last_heartbeat_at=to_iso(now),
            last_message_at=to_iso(now),
            last_sequence=env.sequence,
        )
        await self._eventing.record(
            "NODE_IDENTIFIED",
            source=conn.conn_id,
            node_id=ip.node_id,
            message=f"node identified: {ip.node_name} ({ip.node_type}, fw {ip.firmware_version})",
            severity=Severity.INFO,
            state={"connectivity": CS.ONLINE.value},
        )
        record_audit(
            self._sessions,
            actor=ip.node_id,
            action="identify",
            target=ip.node_id,
            details={
                "name": ip.node_name,
                "type": ip.node_type,
                "firmware_version": ip.firmware_version,
                "capabilities": ip.capabilities,
            },
        )
        self.broadcast_state(ip.node_id, force=True)

        welcome = Envelope(
            protocol_version=PROTOCOL_VERSION,
            message_version=MESSAGE_VERSION,
            message_type=ServerMessageType.WELCOME.value,
            message_id=new_message_id(),
            sequence=0,
            timestamp=now,
            node_id=ip.node_id,
            payload=WelcomePayload(
                accepted=True,
                node_id=ip.node_id,
                server_time=now,
                heartbeat_interval_s=self._settings.heartbeat_interval_s,
                telemetry_interval_s=self._settings.telemetry_interval_s,
            ).model_dump(mode="json"),
        )
        logger.info("node identified", extra={"node_id": ip.node_id, "conn_id": conn.conn_id})
        return [encode_frame(welcome)], False

    async def _handle_heartbeat(self, conn: ConnectionContext, env: Envelope) -> tuple[list[str], bool]:
        assert conn.node_id is not None
        hp = HeartbeatPayload.model_validate(env.payload)
        now = now_utc()
        conn.last_heartbeat_at = now
        conn.uptime_s = hp.uptime_s
        conn.battery_voltage = hp.battery_voltage
        conn.safety_state = hp.safety_state

        node_id = conn.node_id
        fsm = self._node_fsm.get(node_id)
        recovered = False
        if (
            fsm is not None
            and self._runtime[node_id]["connectivity"] == CS.STALE.value
            and fsm.can(CE.HEARTBEAT_OK)
        ):
            fsm.send(CE.HEARTBEAT_OK)
            recovered = True

        self.persist_runtime(
            node_id,
            connectivity=CS.ONLINE.value if recovered else self._runtime[node_id]["connectivity"],
            safety_state=hp.safety_state.value,
            last_heartbeat_at=to_iso(now),
            last_message_at=to_iso(now),
            last_sequence=env.sequence,
            battery_voltage=hp.battery_voltage,
            uptime_s=hp.uptime_s,
        )
        if recovered:
            await self._eventing.record(
                "NODE_RECOVERED",
                source=conn.conn_id,
                node_id=node_id,
                message="heartbeat resumed; node back ONLINE",
                severity=Severity.INFO,
                state={"connectivity": CS.ONLINE.value},
            )
            self.broadcast_state(node_id, force=True)
        else:
            self.broadcast_state(node_id, force=False)
        return [], False

    async def _handle_telemetry(self, conn: ConnectionContext, env: Envelope) -> tuple[list[str], bool]:
        assert conn.node_id is not None
        tp = TelemetryPayload.model_validate(env.payload)
        node_id = conn.node_id
        now = now_utc()

        for sample in tp.samples:
            if sample.quality == "degraded" and self._throttle(f"degraded:{node_id}:{sample.sensor_id}", 5.0):
                await self._eventing.record(
                    "SENSOR_DEGRADED",
                    source=conn.conn_id,
                    node_id=node_id,
                    message=f"sensor {sample.sensor_id} reports degraded quality",
                    severity=Severity.WARNING,
                    state={"sensor_id": sample.sensor_id},
                )

        with self._sessions() as session:
            inserted = ingest(session, node_id, env.message_id, tp, to_iso(now))
        if inserted < len(tp.samples):
            logger.debug(
                "telemetry dedup: %d/%d rows new", inserted, len(tp.samples), extra={"node_id": node_id}
            )

        conn.last_telemetry = {
            s.sensor_id: {"value": s.value, "unit": s.unit, "quality": s.quality, "at": to_iso(now)}
            for s in tp.samples
        }
        self.persist_runtime(
            node_id,
            last_message_at=to_iso(now),
            last_sequence=env.sequence,
            last_telemetry=conn.last_telemetry,
        )
        self.broadcast_state(node_id, force=False)
        return [], False

    async def _handle_ack(self, conn: ConnectionContext, env: Envelope) -> tuple[list[str], bool]:
        assert conn.node_id is not None
        ap = AckPayload.model_validate(env.payload)
        await self._eventing.record(
            "ACK_RECEIVED",
            source=conn.conn_id,
            node_id=conn.node_id,
            message=f"ack for {ap.message_id}: {ap.outcome.value}",
            severity=Severity.DEBUG,
            state={"acked_message_id": ap.message_id, "outcome": ap.outcome.value},
        )
        return [], False

    # --------------------------------------------------------------- helpers

    async def _on_invalid(self, conn: ConnectionContext, result: ValidationResult) -> None:
        env = result.envelope
        await self._reject(conn, env, result.error_code or "PROTOCOL_INVALID", result.error_message or "")
        if result.outcome == VO.MALFORMED:
            self._bump_malformed(conn)
        if self._throttle(f"invalid:{conn.conn_id}:{result.outcome.value}", 2.0):
            severity = Severity.WARNING
            if result.outcome == VO.STALE:
                severity = Severity.INFO
            await self._eventing.record(
                f"PROTOCOL_{result.outcome.value}",
                source=conn.conn_id,
                node_id=conn.node_id,
                message=result.error_message or "invalid frame",
                severity=severity,
            )

    def _bump_malformed(self, conn: ConnectionContext) -> None:
        conn.consecutive_malformed += 1

    async def _malformed_response(self, conn: ConnectionContext) -> tuple[list[str], bool]:
        if conn.consecutive_malformed >= MALFORMED_LIMIT:
            await self._eventing.record(
                "PROTOCOL_MALFORMED_LIMIT",
                source=conn.conn_id,
                node_id=conn.node_id,
                message=f"{conn.consecutive_malformed} consecutive malformed frames; closing connection",
                severity=Severity.ERROR,
            )
            return [], True
        # Explicit outcome for unparseable frames: reject (no envelope to echo)
        await self._reject(conn, None, "PROTOCOL_MALFORMED", "unparseable frame")
        return [], False

    async def _reject(
        self,
        conn: ConnectionContext,
        env: Envelope | None,
        code: str,
        message: str,
        severity: Severity = Severity.WARNING,
    ) -> None:
        node_id = conn.node_id or (env.node_id if env else "")
        payload = RejectPayload(reason=message, error_code=code, message_id=env.message_id if env else None)
        frame = Envelope(
            protocol_version=PROTOCOL_VERSION,
            message_version=MESSAGE_VERSION,
            message_type=ServerMessageType.REJECT.value,
            message_id=new_message_id(),
            sequence=0,
            timestamp=now_utc(),
            node_id=node_id,
            payload=payload.model_dump(mode="json"),
        )
        try:
            await conn.ws.send_text(encode_frame(frame))
        except Exception:  # noqa: BLE001 — client already gone
            logger.debug("failed to send reject to %s", conn.conn_id)
        if severity in (Severity.ERROR, Severity.CRITICAL):
            logger.warning("rejected frame on %s: %s %s", conn.conn_id, code, message)

    def _upsert_node(self, ip: IdentifyPayload) -> None:
        now_iso = to_iso(now_utc())
        with self._sessions() as session:
            node = session.get(Node, ip.node_id)
            if node is None:
                session.add(
                    Node(
                        id=ip.node_id,
                        name=ip.node_name,
                        node_type=ip.node_type,
                        firmware_version=ip.firmware_version,
                        capabilities=ip.capabilities,
                        first_seen_at=now_iso,
                        last_identified_at=now_iso,
                    )
                )
            else:
                node.name = ip.node_name
                node.node_type = ip.node_type
                node.firmware_version = ip.firmware_version
                node.capabilities = ip.capabilities
                node.last_identified_at = now_iso
            if session.get(NodeRuntimeState, ip.node_id) is None:
                session.add(
                    NodeRuntimeState(
                        node_id=ip.node_id,
                        connectivity=CS.DISCONNECTED.value,
                        safety_state=SafetyState.SAFE.value,
                        source_kind=ip.source_kind.value,
                        last_sequence=0,
                        uptime_s=0.0,
                        last_telemetry={},
                        updated_at=now_iso,
                    )
                )
            session.commit()

    def persist_runtime(self, node_id: str, **fields) -> None:
        """Persist runtime fields (DB + in-memory view). One row per node."""
        now_iso = to_iso(now_utc())
        with self._sessions() as session:
            row = session.get(NodeRuntimeState, node_id)
            if row is None:
                row = NodeRuntimeState(node_id=node_id)
                session.add(row)
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = now_iso
            session.commit()
        merged = {**self._runtime.get(node_id, {}), **fields, "updated_at": now_iso}
        merged["node_id"] = node_id
        self._runtime[node_id] = merged

    def broadcast_state(self, node_id: str, *, force: bool) -> None:
        """Broadcast runtime state to frontend clients (throttled to 1/s unless force)."""
        now = now_utc()
        last = self._last_broadcast.get(node_id)
        if not force and last is not None and (now - last).total_seconds() < 1.0:
            return
        self._last_broadcast[node_id] = now
        state = self._runtime.get(node_id)
        if state is not None:
            schedule(self._broadcaster.publish_state_update(node_id, state))

    def _throttle(self, key: str, seconds: float) -> bool:
        now = now_utc()
        last = self._throttle_map.get(key)
        if last is None or (now - last).total_seconds() >= seconds:
            self._throttle_map[key] = now
            return True
        return False

    # ------------------------------------------------------------------- reads

    def node_ids(self) -> list[str]:
        return list(self._runtime.keys())

    def fsm(self, node_id: str) -> object:
        return self._node_fsm.get(node_id)

    def runtime_state(self, node_id: str) -> dict | None:
        return self._runtime.get(node_id)

    def node_state(self, node_id: str) -> dict | None:
        return self._runtime.get(node_id)

    def node_states(self) -> list[dict]:
        return [self._runtime[nid] for nid in sorted(self._runtime)]

    def node_summaries(self) -> list[dict]:
        out = []
        with self._sessions() as session:
            for state in self.node_states():
                node = session.get(Node, state["node_id"])
                if node is None:
                    continue
                summary = node.to_dict()
                summary["state"] = state
                out.append(summary)
        return out
