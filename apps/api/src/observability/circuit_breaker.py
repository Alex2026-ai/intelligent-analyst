"""Circuit breaker implementation with observability.

State transitions are logged and emitted as metrics.
Configuration per dependency from resilience.md.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from apps.api.src.observability.metrics import (
    CIRCUIT_BREAKER_STATE_CHANGE,
    get_metrics,
)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker with configurable thresholds.

    Thresholds come from configuration — not hardcoded (INV-011).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_window_seconds: float = 30.0,
        half_open_max_tries: int = 3,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_window = recovery_window_seconds
        self._half_open_max_tries = half_open_max_tries

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_successes = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_window:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        return False  # OPEN — fail fast

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self._half_open_max_tries:
                self._transition(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_successes = 0

        get_metrics().increment(
            CIRCUIT_BREAKER_STATE_CHANGE,
            breaker=self.name,
            from_state=old_state.value,
            to_state=new_state.value,
        )
