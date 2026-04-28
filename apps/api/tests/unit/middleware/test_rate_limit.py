"""Tests for rate limiting."""

from apps.api.src.middleware.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_within_burst(self):
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        for _ in range(5):
            allowed, retry = limiter.allow("t1")
            assert allowed is True
            assert retry == 0

    def test_rejects_after_burst(self):
        limiter = RateLimiter(requests_per_minute=60, burst_size=3)
        for _ in range(3):
            limiter.allow("t1")
        allowed, retry = limiter.allow("t1")
        assert allowed is False
        assert retry > 0

    def test_different_tenants_independent(self):
        limiter = RateLimiter(requests_per_minute=60, burst_size=2)
        limiter.allow("t1")
        limiter.allow("t1")
        # t1 exhausted, but t2 should still work
        allowed, _ = limiter.allow("t2")
        assert allowed is True

    def test_retry_after_is_positive(self):
        limiter = RateLimiter(requests_per_minute=6, burst_size=1)
        limiter.allow("t1")
        allowed, retry = limiter.allow("t1")
        assert allowed is False
        assert retry >= 1
