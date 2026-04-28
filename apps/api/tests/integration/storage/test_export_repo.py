"""Tests for export metadata repository."""

import pytest
from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.export_repo import ExportRepository


class TestExportRepo:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        repo = ExportRepository(db, "t1")
        await repo.create("e1", "r1", "pdf")
        export = await repo.get("e1")
        assert export["export_id"] == "e1"
        assert export["status"] == "queued"
        assert export["_schema_version"] == 1

    @pytest.mark.asyncio
    async def test_update_status(self, db):
        repo = ExportRepository(db, "t1")
        await repo.create("e1", "r1", "pdf")
        await repo.update_status("e1", "complete", artifact_ref="gs://bucket/file.pdf")
        export = await repo.get("e1")
        assert export["status"] == "complete"
        assert export["artifact_ref"] == "gs://bucket/file.pdf"
        assert export["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_get_not_found(self, db):
        repo = ExportRepository(db, "t1")
        with pytest.raises(DocumentNotFoundError):
            await repo.get("nonexistent")
