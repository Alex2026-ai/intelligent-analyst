"""Tests for config repository — versioned config with history."""

import pytest

from apps.api.src.storage.firestore.config_repo import ConfigRepository


class TestConfigRepo:
    @pytest.mark.asyncio
    async def test_set_and_get(self, db):
        repo = ConfigRepository(db, "t1")
        config = await repo.set_config(
            {"thresholds": {"min_confidence": 0.7}},
            "admin@test.com",
            "Initial config",
        )
        assert config["config_version"] == 1
        retrieved = await repo.get_config()
        assert retrieved is not None
        assert retrieved["thresholds"]["min_confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_version_increments(self, db):
        repo = ConfigRepository(db, "t1")
        await repo.set_config({"v": 1}, "admin", "v1")
        await repo.set_config({"v": 2}, "admin", "v2")
        config = await repo.get_config()
        assert config["config_version"] == 2

    @pytest.mark.asyncio
    async def test_history_tracked(self, db):
        repo = ConfigRepository(db, "t1")
        await repo.set_config({"v": 1}, "admin", "first")
        await repo.set_config({"v": 2}, "admin", "second")
        history = await repo.get_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_config_empty(self, db):
        repo = ConfigRepository(db, "t1")
        assert await repo.get_config() is None
