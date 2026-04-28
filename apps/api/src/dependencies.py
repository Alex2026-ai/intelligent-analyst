"""FastAPI dependency injection — auth context, tenant context, RBAC.

tenant_id comes ONLY from the JWT token, NEVER from request body (INV-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request


class Role(str, Enum):
    """User roles for RBAC enforcement.

    Hierarchy: analyst < reviewer < tenant_admin < platform_admin.
    """

    ANALYST = "analyst"
    REVIEWER = "reviewer"
    TENANT_ADMIN = "tenant_admin"
    PLATFORM_ADMIN = "platform_admin"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.ANALYST: 1,
    Role.REVIEWER: 2,
    Role.TENANT_ADMIN: 3,
    Role.PLATFORM_ADMIN: 4,
}


@dataclass(frozen=True)
class AuthContext:
    """Authenticated user context extracted from JWT token.

    All fields come from the token — never from request body (INV-005).
    """

    user_id: str
    tenant_id: str
    role: Role
    correlation_id: str


def get_auth_context(request: Request) -> AuthContext:
    """Extract auth context from request state (set by auth middleware).

    Raises:
        HTTPException: 401 if auth context not present.
    """
    ctx = getattr(request.state, "auth_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


def require_role(minimum_role: Role):
    """FastAPI dependency that enforces minimum RBAC role.

    Args:
        minimum_role: The minimum role required to access the endpoint.

    Returns:
        Dependency function that checks the authenticated user's role.
    """

    def _check(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        user_level = ROLE_HIERARCHY.get(auth.role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 999)
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient role: requires {minimum_role.value}",
            )
        return auth

    return _check


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    """Extract Idempotency-Key from request header (INV-001)."""
    return idempotency_key


def get_idempotency_repo(request: Request):
    """Get tenant-scoped idempotency repository from app state."""
    from apps.api.src.storage.firestore.idempotency_repo import IdempotencyRepository

    auth = get_auth_context(request)
    db = request.app.state.firestore_client
    return IdempotencyRepository(db=db, tenant_id=auth.tenant_id)
