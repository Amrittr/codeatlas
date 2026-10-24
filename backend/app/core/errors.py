"""Error type shared by every layer, and the handlers that turn errors into JSON."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("codeatlas")


class AppError(Exception):
    """An expected failure with a stable machine-readable code and a user-safe message."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}


def register_error_handlers(app: FastAPI, *, include_tracebacks: bool) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": [str(part) for part in err.get("loc", ())], "message": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body("invalid_request", "The request is missing a field or has an invalid value.", details),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(error_body(code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Tracebacks can quote archive paths from user uploads, so production logs only the type.
        logger.error(
            "Unhandled %s while processing request",
            type(exc).__name__,
            exc_info=exc if include_tracebacks else None,
        )
        return JSONResponse(error_body("internal_error", "Unexpected server error."), status_code=500)
