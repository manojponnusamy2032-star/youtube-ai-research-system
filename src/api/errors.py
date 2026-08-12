"""Global API exception handling utilities."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("yairs.api")


class APIConfigurationError(Exception):
    """Raised when API runtime configuration is invalid."""


def add_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Validation error for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation failed",
                "code": "validation_error",
                "timestamp": datetime.utcnow().isoformat(),
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(APIConfigurationError)
    async def config_exception_handler(request: Request, exc: APIConfigurationError) -> JSONResponse:
        logger.error("Configuration error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "code": "configuration_error",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": message,
                "code": f"http_{exc.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "code": "internal_error",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
