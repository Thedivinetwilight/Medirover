"""Uniform API error format (master directive §15).

{"error": {code, message, category, severity, source,
           recoverable, recommended_action, details}}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.errors import (
    NOT_FOUND,
    VALIDATION_FAILED,
    ErrorCategory,
    MediroverError,
)

logger = logging.getLogger("medirover.api")

_STATUS_BY_CATEGORY: dict[ErrorCategory, int] = {
    ErrorCategory.USER_ERROR: status.HTTP_400_BAD_REQUEST,
    ErrorCategory.CONFIG_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCategory.COMMUNICATION_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCategory.HARDWARE_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCategory.DATABASE_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCategory.PROTOCOL_ERROR: status.HTTP_400_BAD_REQUEST,
    ErrorCategory.SAFETY_ERROR: status.HTTP_409_CONFLICT,
    ErrorCategory.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _status_for(exc: MediroverError) -> int:
    if exc.code is NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if exc.code is VALIDATION_FAILED:
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return _STATUS_BY_CATEGORY[exc.code.category]


def error_response(status_code: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": jsonable_encoder(body)})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(MediroverError)
    async def medirover_error_handler(request: Request, exc: MediroverError) -> JSONResponse:
        return error_response(_status_for(exc), exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = MediroverError(
            "request validation failed",
            code=VALIDATION_FAILED,
            source="api",
            details={"errors": jsonable_encoder(exc.errors())},
        ).to_dict()
        return error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, body)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            body = MediroverError("resource not found", code=NOT_FOUND, source="api").to_dict()
            return error_response(status.HTTP_404_NOT_FOUND, body)
        # Let other HTTP exceptions keep their conventional status codes
        body = MediroverError(str(exc.detail), code=VALIDATION_FAILED, source="api").to_dict()
        return error_response(exc.status_code, body)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: BLE001
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        body = MediroverError(
            f"internal error: {type(exc).__name__}",
            source="api",
        ).to_dict()
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, body)
