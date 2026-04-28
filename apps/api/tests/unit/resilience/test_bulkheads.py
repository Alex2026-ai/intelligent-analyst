"""Tests for bulkhead isolation."""

import asyncio
from apps.api.src.resilience.bulkheads import Bulkhead, BulkheadRegistry


class TestBulkhead:
    def test_acquire_within_limit(self):
        async def _test():
            bh = Bulkhead("test", max_concurrent=3)
            assert await bh.acquire() is True
            assert bh.active_count == 1
            assert bh.available == 2
        asyncio.run(_test())

    def test_reject_at_capacity(self):
        async def _test():
            bh = Bulkhead("test", max_concurrent=2)
            await bh.acquire()
            await bh.acquire()
            assert bh.is_full is True
            assert await bh.acquire() is False
        asyncio.run(_test())

    def test_release_frees_slot(self):
        async def _test():
            bh = Bulkhead("test", max_concurrent=1)
            await bh.acquire()
            assert bh.is_full is True
            bh.release()
            assert bh.is_full is False
            assert await bh.acquire() is True
        asyncio.run(_test())


class TestBulkheadRegistry:
    def test_default_pools(self):
        registry = BulkheadRegistry()
        assert "resolution" in registry.get_all_status()
        assert "review" in registry.get_all_status()
        assert "admin" in registry.get_all_status()

    def test_pools_isolated(self):
        async def _test():
            registry = BulkheadRegistry({"pool_a": 2, "pool_b": 2})
            # Fill pool A
            await registry.get("pool_a").acquire()
            await registry.get("pool_a").acquire()
            assert registry.get("pool_a").is_full is True
            # Pool B still available
            assert await registry.get("pool_b").acquire() is True
        asyncio.run(_test())

    def test_custom_config(self):
        registry = BulkheadRegistry({"custom": 5})
        assert registry.get("custom").available == 5
