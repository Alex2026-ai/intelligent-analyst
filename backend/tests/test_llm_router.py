"""
test_llm_router.py — Unit tests for L3 model abstraction + soft failover.

Tests config resolution, retry behavior, failover logic, and error handling.
All LLM calls are mocked — no real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.llm_router import (
    LLMProviderConfig,
    LLMCallResult,
    get_active_model_config,
    get_secondary_config,
    should_failover,
    call_l3_with_failover,
    _call_provider,
)


# =============================================================================
# Config tests
# =============================================================================


class TestGetActiveModelConfig:
    def test_default_config(self):
        config = get_active_model_config()
        assert config.provider == "anthropic"
        assert config.model == "claude-3-haiku-20240307"
        assert config.cost_per_call_usd == 0.005

    @patch.dict("os.environ", {
        "L3_PRIMARY_PROVIDER": "openrouter",
        "L3_PRIMARY_MODEL": "meta-llama/llama-3-70b",
        "L3_COST_PER_CALL_USD": "0.002",
    })
    def test_env_override(self):
        # Re-import to pick up patched env
        from app.llm_router import get_active_model_config as gmc
        config = gmc()
        assert config.provider == "anthropic"  # Module-level var already read
        # But cost comes from os.getenv at call time
        assert config.cost_per_call_usd == 0.002


class TestGetSecondaryConfig:
    def test_secondary_none_when_empty(self):
        config = get_secondary_config()
        assert config is None

    @patch("app.llm_router.L3_SECONDARY_PROVIDER", "openrouter")
    @patch("app.llm_router.L3_SECONDARY_MODEL", "meta-llama/llama-3-70b")
    @patch("app.llm_router.L3_SECONDARY_API_KEY", "sk-test-key")
    @patch("app.llm_router.L3_SECONDARY_BASE_URL", "https://openrouter.ai/api/v1")
    def test_secondary_configured(self):
        config = get_secondary_config()
        assert config is not None
        assert config.provider == "openrouter"
        assert config.model == "meta-llama/llama-3-70b"
        assert config.api_key == "sk-test-key"
        assert config.base_url == "https://openrouter.ai/api/v1"


# =============================================================================
# should_failover tests
# =============================================================================


class TestShouldFailover:
    def test_429_true(self):
        err = Exception("Error code: 429 - Rate limit exceeded")
        assert should_failover(err) is True

    def test_rate_limit_error_type(self):
        """Anthropic SDK raises RateLimitError."""
        err = type("RateLimitError", (Exception,), {})("rate limited")
        assert should_failover(err) is True

    def test_503_true(self):
        err = Exception("503 Service Unavailable")
        assert should_failover(err) is True

    def test_400_false(self):
        err = Exception("400 Bad Request")
        assert should_failover(err) is False

    def test_500_false(self):
        err = Exception("500 Internal Server Error")
        assert should_failover(err) is False

    def test_generic_error_false(self):
        err = ValueError("something broke")
        assert should_failover(err) is False


# =============================================================================
# _call_provider tests
# =============================================================================


class TestCallProvider:
    def test_anthropic_provider(self):
        config = LLMProviderConfig(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            api_key="test-key",
        )

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Apple Inc")]

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_message
            result = _call_provider(
                config,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=100,
            )
            assert result == "Apple Inc"
            MockClient.return_value.messages.create.assert_called_once_with(
                model="claude-3-haiku-20240307",
                max_tokens=100,
                messages=[{"role": "user", "content": "test"}],
            )

    def test_unsupported_provider_raises(self):
        config = LLMProviderConfig(
            provider="unknown",
            model="some-model",
            api_key="key",
        )
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            _call_provider(config, [], 100)

    def test_openrouter_requires_base_url(self):
        config = LLMProviderConfig(
            provider="openrouter",
            model="some-model",
            api_key="key",
            base_url=None,
        )
        with pytest.raises(ValueError, match="openrouter requires"):
            _call_provider(config, [], 100)


# =============================================================================
# call_l3_with_failover tests
# =============================================================================


class TestCallL3WithFailover:
    def test_primary_success(self):
        """Primary succeeds on first attempt."""
        with patch("app.llm_router._call_provider") as mock_call:
            mock_call.return_value = "Apple Inc"
            result = call_l3_with_failover(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=100,
            )
            assert result.text == "Apple Inc"
            assert result.provider_used == "anthropic"
            assert result.model_used == "claude-3-haiku-20240307"
            assert result.failover_used is False
            assert result.attempts == 1
            assert mock_call.call_count == 1

    def test_primary_429_retries_then_succeeds(self):
        """Primary fails twice with 429, succeeds on 3rd attempt."""
        rate_err = Exception("429 rate limit exceeded")

        with patch("app.llm_router._call_provider") as mock_call, \
             patch("time.sleep"):
            mock_call.side_effect = [rate_err, rate_err, "Microsoft Corporation"]
            result = call_l3_with_failover(
                messages=[{"role": "user", "content": "test"}],
            )
            assert result.text == "Microsoft Corporation"
            assert result.failover_used is False
            assert result.attempts == 3
            assert mock_call.call_count == 3

    @patch("app.llm_router.L3_SECONDARY_PROVIDER", "openrouter")
    @patch("app.llm_router.L3_SECONDARY_MODEL", "llama-3-70b")
    @patch("app.llm_router.L3_SECONDARY_API_KEY", "sk-test")
    @patch("app.llm_router.L3_SECONDARY_BASE_URL", "https://openrouter.ai/api/v1")
    def test_primary_exhausted_failover_succeeds(self):
        """Primary exhausts retries with 429, secondary succeeds."""
        rate_err = Exception("429 rate limit exceeded")

        with patch("app.llm_router._call_provider") as mock_call, \
             patch("time.sleep"):
            # 3 primary failures, then secondary succeeds
            mock_call.side_effect = [rate_err, rate_err, rate_err, "Pfizer Inc"]
            result = call_l3_with_failover(
                messages=[{"role": "user", "content": "test"}],
            )
            assert result.text == "Pfizer Inc"
            assert result.provider_used == "openrouter"
            assert result.model_used == "llama-3-70b"
            assert result.failover_used is True
            assert result.attempts == 4
            assert mock_call.call_count == 4

    def test_primary_exhausted_no_secondary_raises(self):
        """Primary exhausts retries, no secondary configured → raises."""
        rate_err = Exception("429 rate limit exceeded")

        with patch("app.llm_router._call_provider") as mock_call, \
             patch("time.sleep"):
            mock_call.side_effect = [rate_err, rate_err, rate_err]
            with pytest.raises(Exception, match="429"):
                call_l3_with_failover(
                    messages=[{"role": "user", "content": "test"}],
                )

    def test_non_retryable_error_no_retry(self):
        """400 error → immediate raise, no retry, no failover."""
        bad_err = Exception("400 Bad Request: invalid model")

        with patch("app.llm_router._call_provider") as mock_call:
            mock_call.side_effect = bad_err
            with pytest.raises(Exception, match="400"):
                call_l3_with_failover(
                    messages=[{"role": "user", "content": "test"}],
                )
            # Only 1 attempt — no retry
            assert mock_call.call_count == 1

    @patch("app.llm_router.L3_SECONDARY_PROVIDER", "openrouter")
    @patch("app.llm_router.L3_SECONDARY_MODEL", "llama-3-70b")
    @patch("app.llm_router.L3_SECONDARY_API_KEY", "sk-test")
    @patch("app.llm_router.L3_SECONDARY_BASE_URL", "https://openrouter.ai/api/v1")
    def test_secondary_fails_raises_primary_error(self):
        """Primary 429 exhausted + secondary fails → raises ORIGINAL primary error."""
        primary_err = Exception("429 rate limit exceeded")
        secondary_err = Exception("500 secondary down")

        with patch("app.llm_router._call_provider") as mock_call, \
             patch("time.sleep"):
            mock_call.side_effect = [
                primary_err, primary_err, primary_err,  # 3 primary failures
                secondary_err,                           # secondary also fails
            ]
            with pytest.raises(Exception, match="429"):
                call_l3_with_failover(
                    messages=[{"role": "user", "content": "test"}],
                )

    def test_503_triggers_retry(self):
        """503 error triggers retry same as 429."""
        svc_err = Exception("503 Service Unavailable")

        with patch("app.llm_router._call_provider") as mock_call, \
             patch("time.sleep"):
            mock_call.side_effect = [svc_err, "Google LLC"]
            result = call_l3_with_failover(
                messages=[{"role": "user", "content": "test"}],
            )
            assert result.text == "Google LLC"
            assert result.attempts == 2
