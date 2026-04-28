"""Tests for LLM router — primary/failover, kill switch."""

import asyncio
import pytest
from apps.api.src.llm.provider import MockLLMProvider
from apps.api.src.llm.router import LLMRouter


class TestLLMRouter:
    def test_primary_succeeds(self):
        primary = MockLLMProvider(provider_name="primary", default_confidence=0.9)
        secondary = MockLLMProvider(provider_name="secondary", default_confidence=0.7)
        router = LLMRouter(primary, secondary)
        response = asyncio.run(router.resolve("masked content", {}))
        assert response.provider == "primary"

    def test_failover_to_secondary(self):
        primary = MockLLMProvider(provider_name="primary", should_fail=True)
        secondary = MockLLMProvider(provider_name="secondary", default_confidence=0.7)
        router = LLMRouter(primary, secondary)
        response = asyncio.run(router.resolve("masked content", {}))
        assert response.provider == "secondary"

    def test_both_fail_raises(self):
        primary = MockLLMProvider(should_fail=True)
        secondary = MockLLMProvider(should_fail=True)
        router = LLMRouter(primary, secondary)
        with pytest.raises(RuntimeError, match="All LLM providers unavailable"):
            asyncio.run(router.resolve("content", {}))

    def test_kill_switch_blocks(self):
        primary = MockLLMProvider()
        router = LLMRouter(primary, kill_switch_active=True)
        with pytest.raises(RuntimeError, match="kill switch"):
            asyncio.run(router.resolve("content", {}))

    def test_set_kill_switch(self):
        primary = MockLLMProvider()
        router = LLMRouter(primary)
        assert router.kill_switch_active is False
        router.set_kill_switch(True)
        assert router.kill_switch_active is True
        with pytest.raises(RuntimeError):
            asyncio.run(router.resolve("content", {}))

    def test_no_secondary_single_provider(self):
        primary = MockLLMProvider(provider_name="solo")
        router = LLMRouter(primary)
        response = asyncio.run(router.resolve("content", {}))
        assert response.provider == "solo"

    def test_no_secondary_primary_fails(self):
        primary = MockLLMProvider(should_fail=True)
        router = LLMRouter(primary)
        with pytest.raises(RuntimeError):
            asyncio.run(router.resolve("content", {}))


class TestPromptRegistry:
    def test_get_prompt(self):
        from apps.api.src.llm.prompt_registry import get_prompt
        prompt = get_prompt("resolution_analysis", "1.0")
        assert prompt.version == "1.0"
        assert "{content}" in prompt.user_template

    def test_unknown_prompt_raises(self):
        from apps.api.src.llm.prompt_registry import get_prompt
        with pytest.raises(KeyError):
            get_prompt("nonexistent")

    def test_unknown_version_raises(self):
        from apps.api.src.llm.prompt_registry import get_prompt
        with pytest.raises(KeyError):
            get_prompt("resolution_analysis", "99.0")


class TestResponseParser:
    def test_valid_response(self):
        from apps.api.src.llm.response_parser import parse_llm_response
        result = parse_llm_response("Resolution text", 0.85)
        assert result.valid is True
        assert result.confidence == 0.85

    def test_empty_response_invalid(self):
        from apps.api.src.llm.response_parser import parse_llm_response
        result = parse_llm_response("", 0.5)
        assert result.valid is False

    def test_out_of_range_confidence(self):
        from apps.api.src.llm.response_parser import parse_llm_response
        result = parse_llm_response("text", 1.5)
        assert result.valid is False
        assert result.confidence == 1.0  # Clamped
