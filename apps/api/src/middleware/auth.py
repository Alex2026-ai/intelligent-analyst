"""Authentication middleware — OIDC JWT validation and claim extraction.

Validates tokens on every request except health probes.
Extracts tenant_id, user_id, role from token claims (INV-005).
"""

from __future__ import annotations

import time
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from apps.api.src.dependencies import AuthContext, Role

# Paths that skip authentication (exact match)
PUBLIC_PATHS = frozenset({"/health/startup", "/health/ready", "/health/live"})

# Path prefixes that skip authentication (public-read endpoints)
PUBLIC_PREFIXES = (
    "/v1/public-metadata/sample/",
    "/v1/public-metadata/feed",
)


class TokenValidator:
    """Validates JWT tokens. In production, verifies against JWKS endpoint.

    This implementation accepts a pluggable verify function for testability.
    """

    def __init__(self, verify_func: Callable[[str], dict[str, Any] | None] | None = None) -> None:
        self._verify = verify_func or self._default_verify

    @staticmethod
    def _default_verify(token: str) -> dict[str, Any] | None:
        """Default verifier — rejects all tokens. Override via constructor."""
        return None

    def validate(self, token: str) -> dict[str, Any] | None:
        """Validate a bearer token and return decoded claims.

        Returns:
            Dict of claims if valid, None if invalid.
        """
        return self._verify(token)


class AuthMiddleware(BaseHTTPMiddleware):
    """OIDC JWT authentication middleware.

    Validates Authorization: Bearer {token} on every request except health probes.
    Sets request.state.auth_context on success.
    """

    def __init__(self, app: Any, token_validator: TokenValidator) -> None:
        super().__init__(app)
        self.token_validator = token_validator

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip auth for health probes and public-read endpoints
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Extract token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Missing or invalid Authorization header",
                        "correlation_id": getattr(request.state, "correlation_id", ""),
                        "retry": False,
                    }
                },
            )

        token = auth_header[7:]  # Strip "Bearer "
        claims = self.token_validator.validate(token)

        if claims is None:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Invalid or expired token",
                        "correlation_id": getattr(request.state, "correlation_id", ""),
                        "retry": False,
                    }
                },
            )

        # Check required claims
        user_id = claims.get("sub")
        tenant_id = claims.get("tenant_id")
        role_str = claims.get("role")

        if not all([user_id, tenant_id, role_str]):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Token missing required claims (sub, tenant_id, role)",
                        "correlation_id": getattr(request.state, "correlation_id", ""),
                        "retry": False,
                    }
                },
            )

        # Validate role
        try:
            role = Role(role_str)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": f"Unknown role: {role_str}",
                        "correlation_id": getattr(request.state, "correlation_id", ""),
                        "retry": False,
                    }
                },
            )

        # Check expiry
        exp = claims.get("exp")
        if exp is not None and float(exp) < time.time():
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "TOKEN_EXPIRED",
                        "message": "Token has expired",
                        "correlation_id": getattr(request.state, "correlation_id", ""),
                        "retry": False,
                    }
                },
            )

        # Set auth context on request
        request.state.auth_context = AuthContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            correlation_id=getattr(request.state, "correlation_id", ""),
        )

        # Inject tenant identity into the parent server span (via scope ref)
        from apps.api.src.observability.otel import inject_span_identity
        inject_span_identity(
            scope_or_none=request.scope,
            correlation_id=getattr(request.state, "correlation_id", ""),
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return await call_next(request)
