"""Chaos test: full circuit breaker lifecycle."""

import time
from apps.api.src.resilience.circuit_breaker import CircuitBreaker, State
from apps.api.src.resilience.config import CircuitBreakerConfig


class TestFullLifecycle:
    def test_closed_to_open_to_half_open_to_closed(self):
        config = CircuitBreakerConfig(
            failure_threshold=2, failure_window_seconds=30,
            open_duration_seconds=0.02, half_open_probes=1,
            success_to_close=2,
        )
        cb = CircuitBreaker("lifecycle", config)

        # 1. Start CLOSED
        assert cb.state == State.CLOSED

        # 2. Failures → OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb.state == State.OPEN

        # 3. Wait → HALF_OPEN
        time.sleep(0.03)
        assert cb.state == State.HALF_OPEN

        # 4. Successes → CLOSED
        cb.record_success()
        cb.record_success()
        assert cb.state == State.CLOSED

    def test_half_open_failure_reopens(self):
        config = CircuitBreakerConfig(
            failure_threshold=1, failure_window_seconds=30,
            open_duration_seconds=0.01, half_open_probes=1,
            success_to_close=2,
        )
        cb = CircuitBreaker("reopen", config)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == State.HALF_OPEN
        cb.record_failure()
        assert cb.state == State.OPEN
