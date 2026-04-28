"""Tests for review case repository."""

import pytest
from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.review_repo import ReviewRepository


class TestReviewCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        repo = ReviewRepository(db, "t1")
        await repo.create("c1", "r1", "ec1", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")
        case = await repo.get("c1")
        assert case["case_id"] == "c1"
        assert case["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_status(self, db):
        repo = ReviewRepository(db, "t1")
        await repo.create("c1", "r1", "ec1", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")
        await repo.update_status("c1", "decided")
        case = await repo.get("c1")
        assert case["status"] == "decided"

    @pytest.mark.asyncio
    async def test_assign(self, db):
        repo = ReviewRepository(db, "t1")
        await repo.create("c1", "r1", "ec1", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")
        await repo.assign("c1", "reviewer-42")
        case = await repo.get("c1")
        assert case["assigned_to"] == "reviewer-42"
        assert case["status"] == "assigned"

    @pytest.mark.asyncio
    async def test_list_by_status(self, db):
        repo = ReviewRepository(db, "t1")
        await repo.create("c1", "r1", "ec1", "pending", "high", "low_confidence", "2026-03-22T10:00:00Z")
        await repo.create("c2", "r2", "ec2", "decided", "standard", "force_review", "2026-03-22T10:00:00Z")
        pending = await repo.list_by_status("pending")
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_get_not_found(self, db):
        repo = ReviewRepository(db, "t1")
        with pytest.raises(DocumentNotFoundError):
            await repo.get("nonexistent")
