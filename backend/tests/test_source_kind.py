"""source_kind propagation (M8): identify -> runtime state -> persistence.

Rule 13: a node's hardware origin must be reported by the node itself and
must never be silently relabelled. The default is SIMULATED when a
(legacy) node omits the field; HARDWARE must flow through untouched.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine

from backend.config import Settings
from backend.database.engine import make_session_factory
from backend.database.models import Base, NodeRuntimeState
from backend.services.broadcaster import Broadcaster
from backend.services.eventing import EventingService
from backend.services.node_manager import NodeManager
from backend.services.ws_types import WebSocketLike
from shared.constants import MESSAGE_VERSION, PROTOCOL_VERSION
from shared.protocols.codec import encode_frame
from shared.protocols.registry import NodeMessageType
from shared.schemas.envelope import Envelope
from shared.types import Environment
from shared.utils.timeutil import now_utc


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed: list[int] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)


@pytest.fixture
def manager(tmp_path):
    url = f"sqlite:///{tmp_path}/sk.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    settings = Settings(
        environment=Environment.TESTING,
        db_url=url,
        heartbeat_interval_s=0.2,
        telemetry_interval_s=0.1,
        stale_after_s=0.6,
        offline_after_s=1.2,
        supervisor_scan_s=0.05,
        identify_timeout_s=2.0,
        frontend_dir=str(tmp_path / "no-frontend"),
    )
    broadcaster = Broadcaster()
    eventing = EventingService(sessions, broadcaster)
    mgr = NodeManager(settings, sessions, eventing, broadcaster)
    yield mgr, sessions
    engine.dispose()


def _identify_frame(node_id: str, *, source_kind: str | None = None) -> str:
    payload: dict = {
        "node_id": node_id,
        "node_name": f"{node_id}-name",
        "node_type": "motion",
        "firmware_version": "0.9.0",
        "capabilities": ["telemetry"],
    }
    if source_kind is not None:
        payload["source_kind"] = source_kind
    env = Envelope(
        protocol_version=PROTOCOL_VERSION,
        message_version=MESSAGE_VERSION,
        message_type=NodeMessageType.IDENTIFY.value,
        message_id=str(uuid.uuid4()),
        sequence=1,
        timestamp=now_utc(),
        node_id=node_id,
        payload=payload,
    )
    return encode_frame(env)


@pytest.mark.asyncio
async def test_identify_hardware_propagates_end_to_end(manager):
    mgr, sessions = manager
    ws: WebSocketLike = FakeWS()
    conn = mgr.register_connection(ws)
    assert conn is not None
    frames, close = await mgr.handle(conn.conn_id, _identify_frame("motion-hw", source_kind="HARDWARE"))
    assert close is False
    assert len(frames) == 1  # welcome

    state = mgr.runtime_state("motion-hw")
    assert state is not None
    assert state["source_kind"] == "HARDWARE"

    with sessions() as session:
        row = session.get(NodeRuntimeState, "motion-hw")
        assert row is not None
        assert row.source_kind == "HARDWARE"


@pytest.mark.asyncio
async def test_identify_without_source_kind_defaults_simulated(manager):
    mgr, sessions = manager
    ws: WebSocketLike = FakeWS()
    conn = mgr.register_connection(ws)
    assert conn is not None
    frames, close = await mgr.handle(conn.conn_id, _identify_frame("motion-legacy"))
    assert close is False

    assert mgr.runtime_state("motion-legacy")["source_kind"] == "SIMULATED"
    with sessions() as session:
        row = session.get(NodeRuntimeState, "motion-legacy")
        assert row is not None
        assert row.source_kind == "SIMULATED"


def test_restart_preserves_reported_source_kind(manager):
    mgr, sessions = manager
    from backend.database.models import Node

    # seed a registered node with a persisted HARDWARE runtime row
    with sessions() as session:
        session.add(
            Node(
                id="motion-hw",
                name="motion-hw",
                node_type="motion",
                firmware_version="0.9.0",
                capabilities=[],
                first_seen_at=now_utc().isoformat(),
                last_identified_at=now_utc().isoformat(),
            )
        )
        session.add(
            NodeRuntimeState(
                node_id="motion-hw",
                connectivity="DISCONNECTED",
                safety_state="SAFE",
                source_kind="HARDWARE",
                last_sequence=0,
                uptime_s=0.0,
                last_telemetry={},
                updated_at=now_utc().isoformat(),
            )
        )
        session.commit()

    fresh = NodeManager(mgr._settings, sessions, mgr._eventing, mgr._broadcaster)
    fresh.initialize_from_db()
    state = fresh.runtime_state("motion-hw")
    assert state is not None
    assert state["source_kind"] == "HARDWARE"  # never silently relabelled
