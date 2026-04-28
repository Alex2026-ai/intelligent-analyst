"""Tests for audit log repository — append-only enforcement."""

import pytest

from apps.api.src.storage.firestore.audit_repo import AuditRepository


class TestAuditAppendOnly:
    @pytest.mark.asyncio
    async def test_append(self, db):
        repo = AuditRepository(db, "t1")
        entry = await repo.append("u1", "create", "resolution", "r1", {"layer": 1})
        assert entry["action"] == "create"
        assert entry["user_id"] == "u1"
        assert entry["_schema_version"] == 1

    def test_no_update_method(self):
        """Audit repo must not have update or delete methods."""
        assert not hasattr(AuditRepository, "update")
        assert not hasattr(AuditRepository, "delete")
        assert not hasattr(AuditRepository, "remove")

    @pytest.mark.asyncio
    async def test_list_by_resource(self, db):
        repo = AuditRepository(db, "t1")
        await repo.append("u1", "create", "resolution", "r1")
        await repo.append("u1", "update", "resolution", "r1")
        await repo.append("u2", "create", "resolution", "r2")
        entries = await repo.list_by_resource("resolution", "r1")
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_list_all(self, db):
        repo = AuditRepository(db, "t1")
        await repo.append("u1", "create", "resolution", "r1")
        await repo.append("u1", "create", "export", "e1")
        all_entries = await repo.list_all()
        assert len(all_entries) == 2

    @pytest.mark.asyncio
    async def test_multiple_appends_all_preserved(self, db):
        repo = AuditRepository(db, "t1")
        for i in range(10):
            await repo.append("u1", "create", "resolution", f"r{i}")
        assert len(await repo.list_all()) == 10
