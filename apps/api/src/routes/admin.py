"""Admin endpoints — configuration and user management.

Requires tenant_admin+ role (FP-011: no unprotected admin endpoints).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from apps.api.src.dependencies import AuthContext, Role, require_role

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/config")
async def get_config(
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict:
    """Get tenant configuration."""
    return {
        "tenant_id": auth.tenant_id,
        "config": {
            "confidence_threshold": 0.85,
            "high_impact_threshold": 0.95,
            "rate_limit_per_minute": 100,
            "review_sla_hours": 24,
        },
    }


@router.get("/users")
async def list_users(
    auth: AuthContext = Depends(require_role(Role.TENANT_ADMIN)),
) -> dict:
    """List users in the tenant."""
    return {"users": [], "tenant_id": auth.tenant_id}
