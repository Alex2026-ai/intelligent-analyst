"""Tests for PMC config TTL cache — hit, miss, expiry, poisoning, fallback, events."""

import logging
import time

import pytest

from apps.api.src.public_metadata.config import (
    load_policy,
    reset_cache,
    set_cache_ttl,
    get_safe_default_policy,
    DEFAULT_CACHE_TTL_SECONDS,
    PMC_CONFIG_PATH,
    PMC_CONFIG_DOC,
)
from apps.api.src.storage.firestore.client import InMemoryFirestore


def _seed(db, **overrides):
    data = {
        "policy_id": "cached-v1", "version": "1.0", "mode": "curated_hybrid",
        "allow_real_sanitized_samples": True, "require_manual_approval": False,
        "public_anchor_allowlist": ["INV-002", "INV-005", "INV-006"],
        "blocked_tenants": [],
    }
    data.update(overrides)
    db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set(data)


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    set_cache_ttl(DEFAULT_CACHE_TTL_SECONDS)
    yield
    reset_cache()
    set_cache_ttl(DEFAULT_CACHE_TTL_SECONDS)


class TestCachePopulation:
    @pytest.mark.asyncio
    async def test_first_read_populates_cache(self):
        db = InMemoryFirestore()
        _seed(db)
        p = await load_policy(db)
        assert p.policy_id == "cached-v1"

    @pytest.mark.asyncio
    async def test_repeated_reads_use_cache(self, caplog):
        db = InMemoryFirestore()
        _seed(db)
        set_cache_ttl(60)

        await load_policy(db)  # miss → refresh
        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            caplog.clear()
            await load_policy(db)  # should be cache_hit
        events = [r.getMessage() for r in caplog.records if "ia.pmc.config" in r.name]
        assert any("cache_hit" in e for e in events)

    @pytest.mark.asyncio
    async def test_no_firestore_read_on_cache_hit(self):
        db = InMemoryFirestore()
        _seed(db)
        set_cache_ttl(60)

        await load_policy(db)
        # Delete the config — cached version should still return
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).delete()
        p = await load_policy(db)
        assert p.policy_id == "cached-v1"  # from cache, not Firestore


class TestCacheExpiry:
    @pytest.mark.asyncio
    async def test_expired_ttl_refreshes(self):
        db = InMemoryFirestore()
        _seed(db, policy_id="v1")
        set_cache_ttl(0.01)  # 10ms TTL

        p1 = await load_policy(db)
        assert p1.policy_id == "v1"

        # Update Firestore
        _seed(db, policy_id="v2")
        time.sleep(0.02)  # Wait for TTL to expire

        p2 = await load_policy(db)
        assert p2.policy_id == "v2"

    @pytest.mark.asyncio
    async def test_cache_refresh_event_fires(self, caplog):
        db = InMemoryFirestore()
        _seed(db)
        set_cache_ttl(0.01)

        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            await load_policy(db)
        events = [r.getMessage() for r in caplog.records if "ia.pmc.config" in r.name]
        assert any("cache_refresh" in e for e in events)


class TestMalformedData:
    @pytest.mark.asyncio
    async def test_malformed_does_not_overwrite_good_cache(self):
        db = InMemoryFirestore()
        _seed(db, policy_id="good-v1")
        set_cache_ttl(0.01)

        await load_policy(db)  # cache "good-v1"

        # Poison Firestore with invalid mode
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set({
            "policy_id": "bad", "mode": "INVALID_MODE_VALUE",
        })
        time.sleep(0.02)

        p = await load_policy(db)
        # Should return cached "good-v1", not the malformed one
        assert p.policy_id == "good-v1"

    @pytest.mark.asyncio
    async def test_malformed_without_cache_returns_safe_default(self):
        db = InMemoryFirestore()
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).set({
            "mode": "NOT_A_REAL_MODE",
        })
        p = await load_policy(db)
        assert p.policy_id == "pmc-safe-default"


class TestFirestoreFailure:
    @pytest.mark.asyncio
    async def test_failure_with_warm_cache_uses_cached(self):
        db = InMemoryFirestore()
        _seed(db, policy_id="warm-v1")
        set_cache_ttl(0.01)

        await load_policy(db)  # populate cache

        # Simulate failure by clearing data and making TTL expire
        db.collection(PMC_CONFIG_PATH).document(PMC_CONFIG_DOC).delete()
        time.sleep(0.02)

        # Firestore returns None → should use cached "warm-v1"
        p = await load_policy(db)
        assert p.policy_id == "warm-v1"

    @pytest.mark.asyncio
    async def test_failure_without_cache_uses_safe_default(self):
        db = InMemoryFirestore()
        # No config seeded, no cache
        p = await load_policy(db)
        assert p.policy_id == "pmc-safe-default"

    @pytest.mark.asyncio
    async def test_none_db_returns_safe_default(self):
        p = await load_policy(None)
        assert p.policy_id == "pmc-safe-default"


class TestCacheReset:
    @pytest.mark.asyncio
    async def test_reset_clears_cache(self):
        db = InMemoryFirestore()
        _seed(db, policy_id="pre-reset")
        set_cache_ttl(60)

        await load_policy(db)
        reset_cache()

        # After reset, should re-read Firestore
        _seed(db, policy_id="post-reset")
        p = await load_policy(db)
        assert p.policy_id == "post-reset"


class TestConfigEvents:
    @pytest.mark.asyncio
    async def test_miss_event_on_cold_cache(self, caplog):
        db = InMemoryFirestore()
        _seed(db)
        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            await load_policy(db)
        events = [r.getMessage() for r in caplog.records if "ia.pmc.config" in r.name]
        assert any("cache_miss" in e for e in events)

    @pytest.mark.asyncio
    async def test_hit_event_on_warm_cache(self, caplog):
        db = InMemoryFirestore()
        _seed(db)
        set_cache_ttl(60)
        await load_policy(db)
        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            caplog.clear()
            await load_policy(db)
        events = [r.getMessage() for r in caplog.records if "ia.pmc.config" in r.name]
        assert any("cache_hit" in e for e in events)

    @pytest.mark.asyncio
    async def test_fallback_event_on_empty_store(self, caplog):
        db = InMemoryFirestore()
        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            await load_policy(db)
        events = [r.getMessage() for r in caplog.records if "ia.pmc.config" in r.name]
        assert any("cache_fallback_safe_default" in e for e in events)

    @pytest.mark.asyncio
    async def test_no_sensitive_data_in_events(self, caplog):
        db = InMemoryFirestore()
        _seed(db)
        with caplog.at_level(logging.INFO, logger="ia.pmc.config"):
            await load_policy(db)
        for record in caplog.records:
            msg = record.getMessage()
            assert "tenant" not in msg.lower()
            assert "password" not in msg.lower()
            assert "content" not in msg
