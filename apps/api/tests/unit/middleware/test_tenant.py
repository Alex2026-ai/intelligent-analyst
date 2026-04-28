"""Tests for tenant isolation."""

from apps.api.src.dependencies import AuthContext, Role
from apps.api.src.middleware.tenant import verify_tenant_access


class TestTenantIsolation:
    def test_same_tenant_allowed(self):
        auth = AuthContext(user_id="u1", tenant_id="t1", role=Role.ANALYST, correlation_id="")
        assert verify_tenant_access(auth, "t1") is True

    def test_different_tenant_denied(self):
        auth = AuthContext(user_id="u1", tenant_id="t1", role=Role.ANALYST, correlation_id="")
        assert verify_tenant_access(auth, "t2") is False

    def test_platform_admin_cross_tenant(self):
        auth = AuthContext(user_id="u1", tenant_id="t1", role=Role.PLATFORM_ADMIN, correlation_id="")
        assert verify_tenant_access(auth, "t2") is True

    def test_tenant_admin_cannot_cross_tenant(self):
        auth = AuthContext(user_id="u1", tenant_id="t1", role=Role.TENANT_ADMIN, correlation_id="")
        assert verify_tenant_access(auth, "t2") is False

    def test_reviewer_cannot_cross_tenant(self):
        auth = AuthContext(user_id="u1", tenant_id="t1", role=Role.REVIEWER, correlation_id="")
        assert verify_tenant_access(auth, "t2") is False
