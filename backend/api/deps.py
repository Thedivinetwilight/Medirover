"""Request-scoped dependencies (works for HTTP requests and WebSockets)."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from backend.api.context import AppContext


def get_ctx(scope: Any) -> AppContext:
    """Direct (non-Depends) access, used by WebSocket handlers."""
    return scope.app.state.ctx


def get_ctx_http(request: Request) -> AppContext:
    """FastAPI dependency for HTTP routes."""
    return request.app.state.ctx
