"""Application factory.

Lifecycle:
  startup  -> engine, migration check (explicit), services, supervisor task
  shutdown -> supervisor stop, websocket close, engine dispose
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import shared as medirover_shared
from backend.api import (
    routes_events,
    routes_faults,
    routes_health,
    routes_nodes,
    ws_nodes,
    ws_state,
)
from backend.api.errors import register_error_handlers
from backend.config import Settings, load_default_config
from backend.core.logging import configure_logging
from backend.database.engine import check_migrated, create_engine, make_session_factory
from backend.services.broadcaster import Broadcaster
from backend.services.eventing import EventingService
from backend.services.node_manager import NodeManager
from backend.services.node_supervisor import NodeSupervisor

logger = logging.getLogger("medirover.app")


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_default_config()
    configure_logging(settings.log_level, json_logs=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.db_url)
        check_migrated(engine)  # explicit: refuse to start on unmigrated DB
        sessions = make_session_factory(engine)
        broadcaster = Broadcaster()
        eventing = EventingService(sessions, broadcaster)
        node_manager = NodeManager(settings, sessions, eventing, broadcaster)
        node_manager.initialize_from_db()
        supervisor = NodeSupervisor(settings, node_manager, eventing)
        supervisor_task = asyncio.create_task(supervisor.run())

        ctx = AppContext(
            settings=settings,
            engine=engine,
            sessions=sessions,
            broadcaster=broadcaster,
            eventing=eventing,
            node_manager=node_manager,
            supervisor=supervisor,
            supervisor_task=supervisor_task,
        )
        app.state.ctx = ctx
        logger.info(
            "medirover backend started (env=%s, db=%s)",
            settings.environment.value,
            settings.db_url,
        )
        try:
            yield
        finally:
            await supervisor.stop()
            if supervisor_task is not None:
                supervisor_task.cancel()
            await broadcaster.close_all()
            engine.dispose()
            logger.info("medirover backend stopped")

    app = FastAPI(
        title="Medirover API",
        version=medirover_shared.__version__,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(routes_health.router)
    app.include_router(routes_nodes.router)
    app.include_router(routes_events.router)
    app.include_router(routes_faults.router)
    app.include_router(ws_nodes.router)
    app.include_router(ws_state.router)

    frontend_dir = settings.frontend_path
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    else:  # pragma: no cover
        logger.warning("frontend directory not found at %s", frontend_dir)

    return app
