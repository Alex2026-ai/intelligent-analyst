"""Correlation ID middleware — assigns a trace ID to every request.

Every response includes X-Correlation-Id header.
Identity injection (correlation_id) happens here via inject_span_identity.
Span status (OK/Error) is handled by SpanStatusASGIMiddleware — not here.
"""

from __future__ import annotations

import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Assigns correlation ID from request header or generates one."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id

        # Inject correlation_id into the parent server span (via scope ref)
        from apps.api.src.observability.otel import inject_span_identity
        inject_span_identity(
            scope_or_none=request.scope,
            correlation_id=correlation_id,
        )

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id

        # Span status is set by SpanStatusASGIMiddleware — no call needed here.
        return response
