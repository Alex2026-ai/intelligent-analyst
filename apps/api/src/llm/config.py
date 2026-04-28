"""LLM provider configuration — loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM providers.

    All values from environment — no hardcoded secrets (FP-004).
    """

    primary_provider: str = "anthropic"
    primary_model: str = "claude-sonnet-4-20250514"

    secondary_provider: str = ""
    secondary_model: str = ""

    max_tokens: int = 4096
    temperature: float = 0.0

    failure_threshold: int = 5
    recovery_timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Load configuration from environment variables."""
        return cls(
            primary_provider=os.environ.get("LLM_PRIMARY_PROVIDER", "anthropic"),
            primary_model=os.environ.get("LLM_PRIMARY_MODEL", "claude-sonnet-4-20250514"),
            secondary_provider=os.environ.get("LLM_SECONDARY_PROVIDER", ""),
            secondary_model=os.environ.get("LLM_SECONDARY_MODEL", ""),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4096")),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.0")),
        )
