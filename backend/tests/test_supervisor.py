"""Supervisor timeout behavior with an isolated in-memory database.

Known-answer tests: with stale_after=0.6s / offline_after=1.2s, a node
whose last heartbeat is T seconds ago must transition deterministically.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine

from backend.config import Settings
from backend.database.engine import make_session_factory
from backend.database.models import Base, Node
from backend.services.broadcaster import Broadcaster
from backend.services.eventing import EventingService
from backend.services.node_manager import NodeManager
from backend.services.node_supervisor import NodeSupervisor
from shared.types import ConnectivityEvent as CE
from shared.types import ConnectivityState as CS
from shared.types import Environment
from shared.utils.timeutil import now_utc, to_iso


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/sup.db")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    settings = Settings(
        environment=Environment.TESTING,
        db_url=f"sqlite:///{tmp_path}/sup.db",
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
    manager = NodeManager(settings, sessions, eventing, broadcaster)
    with sessions() as session:
        session.add(
            Node(
                id="n1",
                name="N1",
                node_type="motion",
                firmware_version="0.1.0",
                capabilities=[],
                first_seen_at="2026-01-01T00:00:00+00:00",
                last_identified_at="2026-01-01T00:00:00+00:00",
            )
        )
        session.commit()
    manager.initialize_from_db()
    yield settings, manager, eventing
    engine.dispose()


async def test_heartbeat_late_marks_stale(env):
    settings, manager, eventing = env
    # Mirror the real identify path: advance the FSM, then persist state.
    fsm = manager.fsm("n1")
    fsm.send(CE.WS_CONNECTED)
    fsm.send(CE.IDENTIFY_OK)
    manager.persist_runtime(
        "n1",
        connectivity=CS.ONLINE.value,
        last_heartbeat_at=to_iso(now_utc() - timedelta(seconds=1.0)),  # > stale (0.6s)
    )
    sup = NodeSupervisor(settings, manager, eventing)
    await sup._tick_once()
    assert manager.runtime_state("n1")["connectivity"] == CS.STALE.value
    types = [e.event_type for e in eventing.recent]
    assert "NODE_STALE" in types


async def test_heartbeat_timeout_marks_offline(env):
    settings, manager, eventing = env
    fsm = manager.fsm("n1")
    fsm.send(CE.WS_CONNECTED)
    fsm.send(CE.IDENTIFY_OK)
    manager.persist_runtime(
        "n1",
        connectivity=CS.ONLINE.value,
        last_heartbeat_at=to_iso(now_utc() - timedelta(seconds=2.0)),  # > offline (1.2s)
    )
    sup = NodeSupervisor(settings, manager, eventing)
    await sup._tick_once()
    assert manager.runtime_state("n1")["connectivity"] == CS.OFFLINE.value
    types = [e.event_type for e in eventing.recent]
    assert "NODE_OFFLINE" in types
    # OFFLINE is sticky: another tick must not raise or change state
    await sup._tick_once()
    assert manager.runtime_state("n1")["connectivity"] == CS.OFFLINE.value


async def test_offline_node_is_not_touched(env):
    settings, manager, eventing = env
    manager.persist_runtime(
        "n1",
        connectivity=CS.OFFLINE.value,
        last_heartbeat_at=to_iso(now_utc() - timedelta(seconds=60)),
    )
    sup = NodeSupervisor(settings, manager, eventing)
    await sup._tick_once()
    assert manager.runtime_state("n1")["connectivity"] == CS.OFFLINE.value
    types = [e.event_type for e in eventing.recent]
    assert "NODE_STALE" not in types
    assert "NODE_OFFLINE" not in types
