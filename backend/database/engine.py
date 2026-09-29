"""Engine + session factory helpers."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine import create_engine as _sa_create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from shared.errors import CONFIG_INVALID, MediroverError


class DatabaseNotMigratedError(MediroverError):
    def __init__(self) -> None:
        super().__init__(
            "database is not migrated. Run `alembic upgrade head` "
            "(see docs/DEVELOPMENT.md). The backend never migrates silently.",
            code=CONFIG_INVALID,
            source="database",
        )


def create_engine(db_url: str, *, echo: bool = False) -> Engine:
    is_sqlite = db_url.startswith("sqlite")
    kwargs: dict = {"echo": echo}
    if is_sqlite:
        # Local file DB: allow concurrent use within one process, fail fast on lock
        kwargs["connect_args"] = {"timeout": 10}
        kwargs["poolclass"] = QueuePool
    engine = _sa_create_engine(db_url, **kwargs)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def check_migrated(engine: Engine) -> None:
    """Explicit migration check — the app refuses to start on an unmigrated DB."""
    from sqlalchemy import inspect

    try:
        tables = inspect(engine).get_table_names()
    except Exception as exc:
        raise DatabaseNotMigratedError() from exc
    if "alembic_version" not in tables:
        raise DatabaseNotMigratedError()
