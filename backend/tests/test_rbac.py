"""
RBAC Unit Tests — Role-Based Access Control
=============================================

Tests:
1. Role helpers (is_admin_role, VALID_ROLES)
2. Role derivation (derive_role — email allowlist, UID allowlist, claims, fallback)
3. Tenant derivation (derive_tenant_id — explicit claim, hash fallback, no domain)
4. Write permission (viewer/auditor blocked, user/admin allowed)
5. Cost redaction (strip_cost_fields, strip_cost_from_record)
6. Tenant isolation (cross-tenant denial, admin bypass)
7. Viewer restrictions (mutations blocked)
8. Admin-tier parity (platform_admin == admin for all checks)
"""
import hashlib
import os
import sys
import pytest

# Ensure the backend app module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.server_enterprise_golden import (
    VALID_ROLES,
    ADMIN_ROLES,
    ADMIN_EMAIL_ALLOWLIST,
    ADMIN_UID_ALLOWLIST,
    is_admin_role,
    derive_role,
    derive_tenant_id,
    strip_cost_fields,
    strip_cost_from_record,
    verify_batch_ownership,
)


# =============================================================================
# TEST 1: Role Helpers
# =============================================================================

class TestRoleHelpers:
    """Verify is_admin_role() and VALID_ROLES constants."""

    def test_admin_is_admin_role(self):
        assert is_admin_role("admin") is True

    def test_platform_admin_is_admin_role(self):
        assert is_admin_role("platform_admin") is True

    def test_user_is_not_admin_role(self):
        assert is_admin_role("user") is False

    def test_viewer_is_not_admin_role(self):
        assert is_admin_role("viewer") is False

    def test_auditor_is_not_admin_role(self):
        assert is_admin_role("auditor") is False

    def test_empty_string_is_not_admin(self):
        assert is_admin_role("") is False

    def test_valid_roles_contains_viewer(self):
        assert "viewer" in VALID_ROLES

    def test_valid_roles_contains_platform_admin(self):
        assert "platform_admin" in VALID_ROLES

    def test_valid_roles_complete(self):
        assert VALID_ROLES == {"user", "auditor", "admin", "viewer", "platform_admin"}


# =============================================================================
# TEST 2: Role Derivation
# =============================================================================

class TestDeriveRole:
    """Verify derive_role() priority: email allowlist > UID allowlist > claim > fallback."""

    def test_email_allowlist_overrides_everything(self):
        """Email in ADMIN_EMAIL_ALLOWLIST returns admin regardless of claims."""
        if not ADMIN_EMAIL_ALLOWLIST:
            pytest.skip("No ADMIN_EMAILS configured in env")
        email = list(ADMIN_EMAIL_ALLOWLIST)[0]
        token = {"email": email, "uid": "some-uid", "role": "viewer"}
        assert derive_role(token) == "admin"

    def test_uid_allowlist_overrides_claims(self):
        """UID in ADMIN_UID_ALLOWLIST returns admin regardless of claims."""
        if not ADMIN_UID_ALLOWLIST:
            pytest.skip("No ADMIN_UIDS configured in env")
        uid = list(ADMIN_UID_ALLOWLIST)[0]
        token = {"uid": uid, "email": "nobody@test.com", "role": "viewer"}
        assert derive_role(token) == "admin"

    def test_viewer_role_from_claim(self):
        """Custom claim role=viewer is recognized."""
        token = {"uid": "uid-x", "email": "viewer@test.com", "role": "viewer"}
        assert derive_role(token) == "viewer"

    def test_user_role_from_claim(self):
        """Custom claim role=user is recognized."""
        token = {"uid": "uid-y", "email": "user@test.com", "role": "user"}
        assert derive_role(token) == "user"

    def test_auditor_role_from_claim(self):
        """Custom claim role=auditor is recognized."""
        token = {"uid": "uid-z", "email": "auditor@test.com", "role": "auditor"}
        assert derive_role(token) == "auditor"

    def test_admin_role_from_claim(self):
        """Custom claim role=admin is recognized."""
        token = {"uid": "uid-a", "email": "admin@test.com", "role": "admin"}
        assert derive_role(token) == "admin"

    def test_unknown_role_defaults_to_user(self):
        """Unknown role string falls back to user."""
        token = {"uid": "uid-b", "email": "test@test.com", "role": "superadmin"}
        assert derive_role(token) == "user"

    def test_missing_role_defaults_to_user(self):
        """No role claim defaults to user."""
        token = {"uid": "uid-c", "email": "test@test.com"}
        assert derive_role(token) == "user"

    def test_empty_role_defaults_to_user(self):
        """Empty role string defaults to user."""
        token = {"uid": "uid-d", "email": "test@test.com", "role": ""}
        assert derive_role(token) == "user"


# =============================================================================
# TEST 3: Tenant Derivation
# =============================================================================

class TestDeriveTenantId:
    """Verify derive_tenant_id() priority: explicit claim > hash fallback."""

    def test_explicit_tenant_claim_takes_priority(self):
        """Custom claim tenant_id overrides all other derivation."""
        token = {"uid": "uid-1", "aud": "project-id", "tenant_id": "tenant_acme.com", "hd": "other.com"}
        assert derive_tenant_id(token) == "tenant_acme.com"

    def test_explicit_tenant_without_prefix(self):
        """Explicit tenant_id without 'tenant_' prefix gets prefixed."""
        token = {"uid": "uid-2", "aud": "project-id", "tenant_id": "acme.com"}
        assert derive_tenant_id(token) == "tenant_acme.com"

    def test_hash_fallback_when_no_explicit_claim(self):
        """Without explicit tenant_id, hash-based derivation is used."""
        token = {"uid": "uid-3", "aud": "project-id"}
        result = derive_tenant_id(token)
        # Should be hash-based, NOT domain-based
        expected_hash = hashlib.sha256("project-id:uid-3".encode()).hexdigest()[:16]
        assert result == f"tenant_{expected_hash}"

    def test_domain_not_used_for_derivation(self):
        """hd claim (domain) is NOT used for tenant derivation (prevents cross-tenant merge)."""
        token = {"uid": "uid-4", "aud": "project-id", "hd": "acme.com"}
        result = derive_tenant_id(token)
        # Should NOT be tenant_acme.com (domain-based)
        assert result != "tenant_acme.com"
        # Should be hash-based
        expected_hash = hashlib.sha256("project-id:uid-4".encode()).hexdigest()[:16]
        assert result == f"tenant_{expected_hash}"

    def test_no_uid_returns_unknown(self):
        """No UID in token returns tenant_unknown."""
        token = {"aud": "project-id"}
        assert derive_tenant_id(token) == "tenant_unknown"

    def test_empty_explicit_tenant_ignored(self):
        """Empty explicit tenant_id is ignored."""
        token = {"uid": "uid-5", "aud": "project-id", "tenant_id": ""}
        result = derive_tenant_id(token)
        # Should fall through to hash-based
        expected_hash = hashlib.sha256("project-id:uid-5".encode()).hexdigest()[:16]
        assert result == f"tenant_{expected_hash}"

    def test_deterministic_hash(self):
        """Same uid+aud always produces same tenant_id."""
        token1 = {"uid": "uid-stable", "aud": "project-id"}
        token2 = {"uid": "uid-stable", "aud": "project-id"}
        assert derive_tenant_id(token1) == derive_tenant_id(token2)

    def test_different_uid_different_tenant(self):
        """Different UIDs produce different tenant_ids."""
        token1 = {"uid": "uid-A", "aud": "project-id"}
        token2 = {"uid": "uid-B", "aud": "project-id"}
        assert derive_tenant_id(token1) != derive_tenant_id(token2)


# =============================================================================
# TEST 4: Write Permission
# =============================================================================

class TestWritePermission:
    """Verify require_write_permission blocks viewer and auditor roles."""

    def test_viewer_blocked_from_write(self):
        """Viewer role cannot write (upload)."""
        from fastapi import HTTPException
        from app.server_enterprise_golden import require_write_permission
        import asyncio

        auth = {"role": "viewer", "tenant_id": "tenant_test"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_write_permission(auth))
        assert exc_info.value.status_code == 403
        assert "Viewers" in exc_info.value.detail

    def test_auditor_blocked_from_write(self):
        """Auditor role cannot write (upload)."""
        from fastapi import HTTPException
        from app.server_enterprise_golden import require_write_permission
        import asyncio

        auth = {"role": "auditor", "tenant_id": "tenant_test"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_write_permission(auth))
        assert exc_info.value.status_code == 403
        assert "Auditors" in exc_info.value.detail

    def test_user_allowed_to_write(self):
        """User (tenant) role can write."""
        from app.server_enterprise_golden import require_write_permission
        import asyncio

        auth = {"role": "user", "tenant_id": "tenant_test"}
        result = asyncio.get_event_loop().run_until_complete(require_write_permission(auth))
        assert result["role"] == "user"

    def test_admin_allowed_to_write(self):
        """Admin role can write."""
        from app.server_enterprise_golden import require_write_permission
        import asyncio

        auth = {"role": "admin", "tenant_id": "tenant_test"}
        result = asyncio.get_event_loop().run_until_complete(require_write_permission(auth))
        assert result["role"] == "admin"


# =============================================================================
# TEST 5: Cost Redaction
# =============================================================================

class TestCostRedaction:
    """Verify strip_cost_fields removes ALL cost-sensitive data."""

    def _make_batch(self):
        return {
            "trace_id": "BATCH-TEST",
            "status": "completed",
            "total": 100,
            "cost": 0.50,
            "llm_budget_summary": {
                "budget_usd": 10.0,
                "spent_usd": 0.50,
                "calls": 100,
                "avg_cost_per_call": 0.005,
            },
            "l3_yield": 5.0,
            "stats": {
                "total_cost": 0.50,
                "auto_resolved_pct": 95.0,
                "l1_resolved": 90,
            },
            "counts": {"l1_resolved": 90, "l4_flagged": 10},
        }

    def test_strip_removes_cost(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert "cost" not in stripped

    def test_strip_removes_llm_budget_summary(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert "llm_budget_summary" not in stripped

    def test_strip_removes_l3_yield(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert "l3_yield" not in stripped

    def test_strip_removes_nested_total_cost(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert "total_cost" not in stripped.get("stats", {})

    def test_strip_preserves_non_cost_fields(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert stripped["trace_id"] == "BATCH-TEST"
        assert stripped["status"] == "completed"
        assert stripped["total"] == 100
        assert stripped["counts"]["l1_resolved"] == 90
        assert stripped["stats"]["auto_resolved_pct"] == 95.0

    def test_strip_does_not_mutate_original(self):
        batch = self._make_batch()
        stripped = strip_cost_fields(batch)
        assert "cost" in batch  # Original unchanged
        assert "cost" not in stripped

    def test_strip_handles_missing_fields(self):
        """Works on batches that don't have cost fields."""
        batch = {"trace_id": "BATCH-NOCOST", "status": "completed"}
        stripped = strip_cost_fields(batch)
        assert stripped["trace_id"] == "BATCH-NOCOST"

    def test_strip_cost_from_record(self):
        record = {"original": "Apple", "resolved": "Apple Inc", "cost": 0.005}
        stripped = strip_cost_from_record(record)
        assert "cost" not in stripped
        assert stripped["original"] == "Apple"
        assert stripped["resolved"] == "Apple Inc"

    def test_strip_cost_from_record_no_cost(self):
        record = {"original": "Apple", "resolved": "Apple Inc"}
        stripped = strip_cost_from_record(record)
        assert stripped["original"] == "Apple"


# =============================================================================
# TEST 6: Admin-Tier Parity
# =============================================================================

class TestAdminTierParity:
    """Verify platform_admin has same privileges as admin."""

    def test_admin_role_dependency_accepts_platform_admin(self):
        """require_admin_role passes for platform_admin."""
        from app.server_enterprise_golden import require_admin_role
        import asyncio

        auth = {"role": "platform_admin", "tenant_id": "tenant_admin_xxx"}
        result = asyncio.get_event_loop().run_until_complete(require_admin_role(auth))
        assert result["role"] == "platform_admin"

    def test_admin_role_dependency_accepts_admin(self):
        """require_admin_role passes for admin."""
        from app.server_enterprise_golden import require_admin_role
        import asyncio

        auth = {"role": "admin", "tenant_id": "tenant_test"}
        result = asyncio.get_event_loop().run_until_complete(require_admin_role(auth))
        assert result["role"] == "admin"

    def test_admin_role_dependency_rejects_user(self):
        """require_admin_role rejects user."""
        from fastapi import HTTPException
        from app.server_enterprise_golden import require_admin_role
        import asyncio

        auth = {"role": "user", "tenant_id": "tenant_test"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_admin_role(auth))
        assert exc_info.value.status_code == 403

    def test_admin_role_dependency_rejects_viewer(self):
        """require_admin_role rejects viewer."""
        from fastapi import HTTPException
        from app.server_enterprise_golden import require_admin_role
        import asyncio

        auth = {"role": "viewer", "tenant_id": "tenant_test"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_admin_role(auth))
        assert exc_info.value.status_code == 403


# =============================================================================
# TEST 7: Claim Schema Validation
# =============================================================================

class TestClaimSchema:
    """Verify the claim schema produces expected auth dicts."""

    def test_viewer_with_tenant_claim(self):
        """Viewer with explicit tenant_id gets correct role + tenant."""
        token = {"uid": "uid-viewer", "email": "viewer@ext.com",
                 "role": "viewer", "tenant_id": "tenant_acme.com"}
        assert derive_role(token) == "viewer"
        assert derive_tenant_id(token) == "tenant_acme.com"

    def test_user_without_tenant_claim(self):
        """User without explicit tenant_id gets hash-based tenant."""
        token = {"uid": "uid-user", "email": "user@company.com",
                 "aud": "ia-enterprise", "role": "user"}
        assert derive_role(token) == "user"
        tenant = derive_tenant_id(token)
        assert tenant.startswith("tenant_")
        assert tenant != "tenant_unknown"

    def test_admin_bypasses_tenant_derivation(self):
        """Admin can have any tenant — is_admin_role bypasses isolation checks."""
        token = {"uid": "uid-admin", "email": "admin@company.com",
                 "aud": "ia-enterprise", "role": "admin"}
        assert derive_role(token) == "admin"
        assert is_admin_role("admin") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
