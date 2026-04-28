"""Chaos test: LLM provider failover."""

import asyncio
from apps.api.src.llm.provider import MockLLMProvider
from apps.api.src.llm.router import LLMRouter


class TestLLMFailover:
    def test_failover_on_primary_failure(self):
        primary = MockLLMProvider(provider_name="A", should_fail=True)
        secondary = MockLLMProvider(provider_name="B", default_confidence=0.7)
        router = LLMRouter(primary, secondary)
        response = asyncio.run(router.resolve("masked content", {}))
        assert response.provider == "B"

    def test_full_outage_raises(self):
        primary = MockLLMProvider(provider_name="A", should_fail=True)
        secondary = MockLLMProvider(provider_name="B", should_fail=True)
        router = LLMRouter(primary, secondary)
        import pytest
        with pytest.raises(RuntimeError, match="unavailable"):
            asyncio.run(router.resolve("content", {}))

    def test_kill_switch_blocks_all(self):
        primary = MockLLMProvider()
        router = LLMRouter(primary, kill_switch_active=True)
        import pytest
        with pytest.raises(RuntimeError, match="kill switch"):
            asyncio.run(router.resolve("content", {}))
