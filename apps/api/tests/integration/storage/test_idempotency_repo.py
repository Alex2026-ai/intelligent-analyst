"""Tests for idempotency repository."""

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.src.storage.firestore.client import InMemoryFirestore
from apps.api.src.storage.firestore.idempotency_repo import IdempotencyRepository


class TestIdempotencyRepo:
    @pytest.mark.asyncio
    async def test_put_then_get(self):
        db = InMemoryFirestore()
        repo = IdempotencyRepository(db, "t1")
        await repo.put("key-1", {"resolution_id": "r1", "status": "resolved"})
        result = await repo.get("key-1")
        assert result is not None
        assert result["resolution_id"] == "r1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        db = InMemoryFirestore()
        repo = IdempotencyRepository(db, "t1")
        assert await repo.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_duplicate_key_returns_same(self):
        db = InMemoryFirestore()
        repo = IdempotencyRepository(db, "t1")
        await repo.put("key-1", {"data": "first"})
        result = await repo.get("key-1")
        assert result["data"] == "first"

    @pytest.mark.asyncio
    async def test_expired_key_returns_none(self):
        db = InMemoryFirestore()
        repo = IdempotencyRepository(db, "t1")
        # Manually store an expired entry
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        db.collection("tenants/t1/idempotency_keys").document("expired-key").set({
            "response": {"data": "old"},
            "created_at": past,
            "expires_at": past,
        })
        result = await repo.get("expired-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_tenant_scoped(self):
        db = InMemoryFirestore()
        repo_a = IdempotencyRepository(db, "tenant-A")
        repo_b = IdempotencyRepository(db, "tenant-B")
        await repo_a.put("key-1", {"tenant": "A"})
        assert await repo_b.get("key-1") is None
        result = await repo_a.get("key-1")
        assert result["tenant"] == "A"
