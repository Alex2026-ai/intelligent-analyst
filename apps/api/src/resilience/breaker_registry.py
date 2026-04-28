"""Registry of all circuit breakers — one per external dependency."""

from __future__ import annotations

from typing import Callable

from apps.api.src.resilience.circuit_breaker import CircuitBreaker, State
from apps.api.src.resilience.config import BREAKER_CONFIGS, CircuitBreakerConfig


class BreakerRegistry:
    """Manages circuit breakers for all external dependencies."""

    def __init__(
        self,
        on_state_change: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._on_state_change = on_state_change

        # Initialize all configured breakers
        for name, config in BREAKER_CONFIGS.items():
            self._breakers[name] = CircuitBreaker(name, config, on_state_change)

    def get(self, name: str) -> CircuitBreaker:
        """Get a circuit breaker by dependency name.

        Raises KeyError if not found.
        """
        return self._breakers[name]

    def get_all_states(self) -> dict[str, str]:
        """Get current state of all circuit breakers."""
        return {name: cb.state.value for name, cb in self._breakers.items()}

    def any_open(self) -> bool:
        """Check if any circuit breaker is currently open."""
        return any(cb.state == State.OPEN for cb in self._breakers.values())

    def all_closed(self) -> bool:
        """Check if all circuit breakers are closed."""
        return all(cb.state == State.CLOSED for cb in self._breakers.values())

    @property
    def names(self) -> list[str]:
        return list(self._breakers.keys())
