"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from backend.api.context import AppContext
from backend.api.deps import get_ctx_http
from backend.schemas.api import HealthResponse
from shared import __version__
from shared.types import SourceKind
from shared.utils.timeutil import now_utc, to_iso

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(ctx: AppContext = Depends(get_ctx_http)) -> HealthResponse:
    db_status = "ok"
    try:
        with ctx.sessions() as session:
            session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    source = SourceKind.HARDWARE if ctx.settings.environment.value == "hardware" else SourceKind.SIMULATED
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=__version__,
        environment=ctx.settings.environment,
        source_kind=source,
        server_time=to_iso(now_utc()),
        database=db_status,
    )
