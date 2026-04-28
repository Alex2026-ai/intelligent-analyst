"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    """Structured response from an LLM provider."""
    resolution: str
    confidence: float
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    raw_response: str = ""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @abstractmethod
    async def resolve(
        self,
        masked_content: str,
        context: dict[str, Any],
        prompt_version: str,
    ) -> LLMResponse:
        """Send masked content to LLM and return structured response.

        Args:
            masked_content: PII-masked document content.
            context: Additional context (document_type, metadata).
            prompt_version: Version of the prompt to use.

        Returns:
            Structured LLMResponse.
        """


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(
        self,
        provider_name: str = "mock",
        model: str = "mock-model",
        default_confidence: float = 0.85,
        should_fail: bool = False,
    ) -> None:
        self._name = provider_name
        self._model = model
        self._confidence = default_confidence
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    async def resolve(
        self,
        masked_content: str,
        context: dict[str, Any],
        prompt_version: str,
    ) -> LLMResponse:
        if self._should_fail:
            raise ConnectionError(f"Provider {self._name} unavailable")
        return LLMResponse(
            resolution=f"LLM resolution for: {masked_content[:50]}",
            confidence=self._confidence,
            provider=self._name,
            model=self._model,
            prompt_version=prompt_version,
            latency_ms=150,
        )
