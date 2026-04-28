"""Tenant isolation middleware — ensures all operations are tenant-scoped.

tenant_id comes ONLY from the JWT token (INV-005).
No cross-tenant data access — ever.
"""

from __future__ import annotations

from apps.api.src.dependencies import AuthContext


def verify_tenant_access(auth: AuthContext, resource_tenant_id: str) -> bool:
    """Verify the authenticated user has access to the resource's tenant.

    Platform admins can access any tenant. All other roles can only
    access their own tenant.

    Args:
        auth: Authenticated user context.
        resource_tenant_id: Tenant ID of the resource being accessed.

    Returns:
        True if access is allowed.
    """
    from apps.api.src.dependencies import Role

    if auth.role == Role.PLATFORM_ADMIN:
        return True
    return auth.tenant_id == resource_tenant_id
