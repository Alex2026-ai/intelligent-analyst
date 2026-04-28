"""Tests for circuit breaker state machine."""

import time
from apps.api.src.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError, State
from apps.api.src.resilience.config import CircuitBreakerConfig


def _config(threshold=3, open_secs=0.05, success_to_close=2):
    return CircuitBreakerConfig(
        failure_threshold=threshold, failure_window_seconds=30,
        open_duration_seconds=open_secs, half_open_probes=1,
        success_to_close=success_to_close,
    )


class TestCircuitBreakerStates:
    def test_starts_closed(self):
        cb = CircuitBreaker("test", _config())
        assert cb.state == State.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", _config(threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state == State.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", _config(threshold=2, open_secs=0.01))
        cb.record_failure()
        cb.record_failure()
        assert cb.state == State.OPEN
        time.sleep(0.02)
        assert cb.state == State.HALF_OPEN
        assert cb.allow_request() is True

    def test_closes_after_successes_in_half_open(self):
        cb = CircuitBreaker("test", _config(threshold=2, open_secs=0.01, success_to_close=2))
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == State.HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == State.CLOSED

    def test_reopens_on_half_open_failure(self):
        cb = CircuitBreaker("test", _config(threshold=2, open_secs=0.01))
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        # Trigger half-open transition
        assert cb.state == State.HALF_OPEN
        # Fail in half-open — should reopen with longer timeout
        cb.record_failure()
        # Internal state is OPEN (check _state directly to avoid timeout re-trigger)
        assert cb._state == State.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", _config(threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == State.CLOSED  # Reset by success

    def test_remaining_open_time(self):
        cb = CircuitBreaker("test", _config(threshold=1, open_secs=10))
        cb.record_failure()
        assert cb.remaining_open_time() > 0

    def test_remaining_time_zero_when_closed(self):
        cb = CircuitBreaker("test", _config())
        assert cb.remaining_open_time() == 0.0


class TestStateChangeCallback:
    def test_callback_on_open(self):
        changes = []
        def on_change(name, old, new):
            changes.append((name, old, new))
        cb = CircuitBreaker("test-cb", _config(threshold=2), on_state_change=on_change)
        cb.record_failure()
        cb.record_failure()
        assert len(changes) == 1
        assert changes[0] == ("test-cb", "closed", "open")
