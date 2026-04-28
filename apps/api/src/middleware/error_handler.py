"""Global error handler — structured error responses matching contracts.md.

Never exposes stack traces, internal paths, or implementation details.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ia_shared.models.errors import (
    AUTHENTICATION_REQUIRED,
    INSUFFICIENT_ROLE,
    RATE_LIMIT_EXCEEDED,
    RESOURCE_NOT_FOUND,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
)

# Map HTTP status codes to default error codes
STATUS_TO_CODE: dict[int, str] = {
    400: VALIDATION_ERROR,
    401: AUTHENTICATION_REQUIRED,
    403: INSUFFICIENT_ROLE,
    404: RESOURCE_NOT_FOUND,
    429: RATE_LIMIT_EXCEEDED,
    503: SERVICE_DEGRADED,
}


def make_error_response(
    status_code: int,
    code: str,
    message: str,
    correlation_id: str = "",
    retry: bool = False,
) -> JSONResponse:
    """Create a structured error response matching contracts.md format."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id,
                "retry": retry,
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTPExceptions with structured error format."""
    correlation_id = getattr(request.state, "correlation_id", "")
    code = STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR")
    retry = exc.status_code in {429, 503}

    return make_error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        correlation_id=correlation_id,
        retry=retry,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions — never expose internals."""
    correlation_id = getattr(request.state, "correlation_id", "")
    return make_error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An internal error occurred. Contact support with the correlation ID.",
        correlation_id=correlation_id,
        retry=False,
    )
