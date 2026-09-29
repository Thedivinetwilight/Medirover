"""App context: the shared service container attached to app.state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings
from backend.services.broadcaster import Broadcaster
from backend.services.eventing import EventingService
from backend.services.node_manager import NodeManager
from backend.services.node_supervisor import NodeSupervisor


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    broadcaster: Broadcaster
    eventing: EventingService
    node_manager: NodeManager
    supervisor: NodeSupervisor
    supervisor_task: asyncio.Task | None = None
