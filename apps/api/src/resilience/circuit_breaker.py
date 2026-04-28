"""Circuit breaker with state machine, metrics, and logging.

State transitions emit structured logs and metrics.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, TypeVar

from apps.api.src.resilience.config import CircuitBreakerConfig

T = TypeVar("T")


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when circuit is open and call is rejected."""

    def __init__(self, name: str, remaining_seconds: float) -> None:
        super().__init__(f"Circuit '{name}' is open. Retry in {remaining_seconds:.1f}s")
        self.name = name
        self.remaining_seconds = remaining_seconds


class CircuitBreaker:
    """Generic circuit breaker with configurable thresholds.

    All state transitions emit metrics via the on_state_change callback.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig,
        on_state_change: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.name = name
        self._config = config
        self._on_state_change = on_state_change

        self._state = State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0

    @property
    def state(self) -> State:
        if self._state == State.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._config.open_duration_seconds:
                self._transition(State.HALF_OPEN)
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        current = self.state
        return current != State.OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == State.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_to_close:
                self._transition(State.CLOSED)
        elif self._state == State.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._last_failure_time = time.monotonic()
        if self._state == State.HALF_OPEN:
            self._transition(State.OPEN)
        elif self._state == State.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self._config.failure_threshold:
                self._transition(State.OPEN)

    def _transition(self, new_state: State) -> None:
        old_state = self._state
        self._state = new_state

        if new_state == State.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == State.OPEN:
            self._opened_at = time.monotonic()
            self._success_count = 0
        elif new_state == State.HALF_OPEN:
            self._success_count = 0

        if self._on_state_change:
            self._on_state_change(self.name, old_state.value, new_state.value)

    def remaining_open_time(self) -> float:
        """Seconds remaining before transition to half-open."""
        if self._state != State.OPEN:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self._config.open_duration_seconds - elapsed)
