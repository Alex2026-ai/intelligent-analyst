"""LLM routing — primary/failover provider selection with circuit breakers.

Checks kill switches before every call.
PII masking happens BEFORE this layer (INV-006).
"""

from __future__ import annotations

from typing import Any

from apps.api.src.llm.provider import LLMProvider, LLMResponse
from apps.api.src.observability.circuit_breaker import CircuitBreaker, CircuitState


class LLMRouter:
    """Routes LLM calls to primary provider with failover to secondary.

    Respects circuit breakers and kill switches.
    """

    def __init__(
        self,
        primary: LLMProvider,
        secondary: LLMProvider | None = None,
        primary_breaker: CircuitBreaker | None = None,
        secondary_breaker: CircuitBreaker | None = None,
        kill_switch_active: bool = False,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._primary_breaker = primary_breaker or CircuitBreaker(
            f"llm_{primary.name}", failure_threshold=5, recovery_window_seconds=30
        )
        self._secondary_breaker = secondary_breaker or (
            CircuitBreaker(f"llm_{secondary.name}", failure_threshold=5, recovery_window_seconds=30)
            if secondary else None
        )
        self._kill_switch = kill_switch_active

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def set_kill_switch(self, active: bool) -> None:
        """Enable or disable the LLM kill switch."""
        self._kill_switch = active

    async def resolve(
        self,
        masked_content: str,
        context: dict[str, Any],
        prompt_version: str = "1.0",
    ) -> LLMResponse:
        """Route to primary provider, failover to secondary on error.

        Args:
            masked_content: PII-masked content (INV-006 already applied).
            context: Additional context dict.
            prompt_version: Prompt version to use.

        Returns:
            LLMResponse from whichever provider succeeded.

        Raises:
            RuntimeError: If kill switch active or both providers unavailable.
        """
        if self._kill_switch:
            raise RuntimeError("LLM calls disabled via kill switch")

        # Try primary
        if self._primary_breaker.allow_request():
            try:
                response = await self._primary.resolve(masked_content, context, prompt_version)
                self._primary_breaker.record_success()
                return response
            except Exception:
                self._primary_breaker.record_failure()

        # Failover to secondary
        if self._secondary and self._secondary_breaker and self._secondary_breaker.allow_request():
            try:
                response = await self._secondary.resolve(masked_content, context, prompt_version)
                self._secondary_breaker.record_success()
                return response
            except Exception:
                self._secondary_breaker.record_failure()

        raise RuntimeError("All LLM providers unavailable")
