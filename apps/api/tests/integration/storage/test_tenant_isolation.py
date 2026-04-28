"""Tests for cross-tenant access prevention at the storage layer."""

import pytest

from apps.api.src.storage.firestore.resolution_repo import ResolutionRepository
from apps.api.src.storage.firestore.audit_repo import AuditRepository
from apps.api.src.storage.firestore.review_repo import ReviewRepository


class TestTenantIsolationStorage:
    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_resolutions(self, db):
        repo_a = ResolutionRepository(db, "tenant-A")
        repo_b = ResolutionRepository(db, "tenant-B")
        await repo_a.create("r1", "d1", "resolved", 1, 1.0, "ec1")
        await repo_b.create("r2", "d2", "resolved", 1, 1.0, "ec2")

        # Tenant A should only see r1
        a_resolved = await repo_a.list_by_status("resolved")
        assert len(a_resolved) == 1
        assert a_resolved[0]["resolution_id"] == "r1"

        # Tenant B should only see r2
        b_resolved = await repo_b.list_by_status("resolved")
        assert len(b_resolved) == 1
        assert b_resolved[0]["resolution_id"] == "r2"

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_audit(self, db):
        audit_a = AuditRepository(db, "tenant-A")
        audit_b = AuditRepository(db, "tenant-B")
        await audit_a.append("u1", "create", "resolution", "r1")
        await audit_b.append("u2", "create", "resolution", "r2")

        assert len(await audit_a.list_all()) == 1
        assert len(await audit_b.list_all()) == 1

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_reviews(self, db):
        review_a = ReviewRepository(db, "tenant-A")
        review_b = ReviewRepository(db, "tenant-B")
        await review_a.create("c1", "r1", "ec1", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")
        await review_b.create("c2", "r2", "ec2", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")

        assert len(await review_a.list_by_status("pending")) == 1
        assert len(await review_b.list_by_status("pending")) == 1

    def test_no_cross_tenant_path(self, db):
        """Verify base path is always tenant-scoped."""
        repo = ResolutionRepository(db, "my-tenant")
        assert repo._base_path == "tenants/my-tenant"
