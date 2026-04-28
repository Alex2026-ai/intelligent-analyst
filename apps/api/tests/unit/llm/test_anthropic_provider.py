"""Tests for AnthropicProvider — mock client, no real API calls."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.api.src.llm.anthropic_provider import AnthropicProvider
from apps.api.src.llm.config import LLMConfig


class TestAnthropicProviderInit:
    def test_missing_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicProvider(api_key="")

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic"):
                provider = AnthropicProvider()
                assert provider.name == "anthropic"

    def test_explicit_api_key(self):
        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")
            assert provider.name == "anthropic"


class TestParseResponse:
    def test_valid_json(self):
        result = AnthropicProvider._parse_response(
            '{"resolution": "Compliance finding", "confidence": 0.92, "reasoning": "Clear match"}'
        )
        assert result["resolution"] == "Compliance finding"
        assert result["confidence"] == 0.92

    def test_json_with_surrounding_text(self):
        result = AnthropicProvider._parse_response(
            'Here is my analysis:\n{"resolution": "Match found", "confidence": 0.85}\nDone.'
        )
        assert result["resolution"] == "Match found"
        assert result["confidence"] == 0.85

    def test_invalid_json_fallback(self):
        result = AnthropicProvider._parse_response("This is just plain text")
        assert result["resolution"] == "This is just plain text"
        assert result["confidence"] == 0.0

    def test_empty_response(self):
        result = AnthropicProvider._parse_response("")
        assert result["resolution"] == ""
        assert result["confidence"] == 0.0

    def test_malformed_json(self):
        result = AnthropicProvider._parse_response('{"resolution": "incomplete')
        assert result["confidence"] == 0.0


class TestBuildSystemPrompt:
    def test_includes_document_type(self):
        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")
            prompt = provider._build_system_prompt(
                {"document_type": "regulatory"}, "1.0"
            )
            assert "regulatory" in prompt
            assert "1.0" in prompt

    def test_includes_pii_masking_notice(self):
        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")
            prompt = provider._build_system_prompt({}, "1.0")
            assert "PII-masked" in prompt

    def test_requests_json_format(self):
        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")
            prompt = provider._build_system_prompt({}, "1.0")
            assert '"resolution"' in prompt
            assert '"confidence"' in prompt


class TestResolve:
    def test_successful_call(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"resolution": "SOX compliance", "confidence": 0.91}')
        ]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="test-key")
            result = asyncio.run(
                provider.resolve(
                    "Masked document content [SSN_1]",
                    {"document_type": "compliance"},
                    "1.0",
                )
            )

        assert result.resolution == "SOX compliance"
        assert result.confidence == 0.91
        assert result.provider == "anthropic"
        assert result.prompt_version == "1.0"
        assert result.latency_ms >= 0

    def test_empty_response_content(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = []
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="test-key")
            result = asyncio.run(
                provider.resolve("content", {}, "1.0")
            )

        assert result.confidence == 0.0
        assert result.resolution == ""

    def test_non_json_response(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Just a plain text analysis")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("apps.api.src.llm.anthropic_provider.anthropic.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="test-key")
            result = asyncio.run(
                provider.resolve("content", {}, "1.0")
            )

        assert result.resolution == "Just a plain text analysis"
        assert result.confidence == 0.0


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.primary_provider == "anthropic"
        assert config.primary_model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 4096
        assert config.temperature == 0.0

    def test_from_env(self):
        with patch.dict("os.environ", {
            "LLM_PRIMARY_MODEL": "claude-haiku-4-5-20251001",
            "LLM_MAX_TOKENS": "2048",
        }):
            config = LLMConfig.from_env()
            assert config.primary_model == "claude-haiku-4-5-20251001"
            assert config.max_tokens == 2048

    def test_frozen(self):
        config = LLMConfig()
        assert config.__dataclass_params__.frozen is True
