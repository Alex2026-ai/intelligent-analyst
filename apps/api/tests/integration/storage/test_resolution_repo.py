"""Tests for resolution repository."""

import pytest
from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.resolution_repo import ResolutionRepository


class TestResolutionCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        repo = ResolutionRepository(db, "t1")
        await repo.create("r1", "d1", "resolved", 1, 0.95, "ec1", "Matched")
        result = await repo.get("r1")
        assert result["resolution_id"] == "r1"
        assert result["status"] == "resolved"
        assert result["_schema_version"] == 1

    @pytest.mark.asyncio
    async def test_get_not_found(self, db):
        repo = ResolutionRepository(db, "t1")
        with pytest.raises(DocumentNotFoundError):
            await repo.get("nonexistent")

    @pytest.mark.asyncio
    async def test_get_by_document_id(self, db):
        repo = ResolutionRepository(db, "t1")
        await repo.create("r1", "doc-abc", "resolved", 2, 0.8, "ec1")
        result = await repo.get_by_document_id("doc-abc")
        assert result is not None
        assert result["resolution_id"] == "r1"

    @pytest.mark.asyncio
    async def test_get_by_document_id_not_found(self, db):
        repo = ResolutionRepository(db, "t1")
        assert await repo.get_by_document_id("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_by_status(self, db):
        repo = ResolutionRepository(db, "t1")
        await repo.create("r1", "d1", "resolved", 1, 1.0, "ec1")
        await repo.create("r2", "d2", "routed_to_review", None, 0.3, "ec2")
        await repo.create("r3", "d3", "resolved", 2, 0.9, "ec3")
        resolved = await repo.list_by_status("resolved")
        assert len(resolved) == 2
