"""Tests for circuit breaker with observability."""

import time

from apps.api.src.observability.circuit_breaker import CircuitBreaker, CircuitState
from apps.api.src.observability.metrics import CIRCUIT_BREAKER_STATE_CHANGE, get_metrics


class TestCircuitBreakerStates:
    def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_recovery_window(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_window_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_closes_after_half_open_successes(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_window_seconds=0.01, half_open_max_tries=2)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_half_open_failure(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_window_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Reset by success


class TestCircuitBreakerMetrics:
    def test_emits_state_change_metric(self):
        metrics = get_metrics()
        metrics.clear()
        cb = CircuitBreaker("test-metric", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        count = metrics.get_counter(
            CIRCUIT_BREAKER_STATE_CHANGE,
            breaker="test-metric",
            from_state="closed",
            to_state="open",
        )
        assert count >= 1.0
