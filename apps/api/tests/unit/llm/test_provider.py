"""Tests for LLM provider interface."""

import asyncio
import pytest
from apps.api.src.llm.provider import MockLLMProvider


class TestMockProvider:
    def test_successful_resolution(self):
        provider = MockLLMProvider(provider_name="test-a", default_confidence=0.9)
        response = asyncio.run(provider.resolve("masked content", {}, "1.0"))
        assert response.confidence == 0.9
        assert response.provider == "test-a"
        assert response.prompt_version == "1.0"

    def test_failing_provider(self):
        provider = MockLLMProvider(should_fail=True)
        with pytest.raises(ConnectionError):
            asyncio.run(provider.resolve("content", {}, "1.0"))

    def test_provider_name(self):
        provider = MockLLMProvider(provider_name="anthropic")
        assert provider.name == "anthropic"
