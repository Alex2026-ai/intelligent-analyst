"""Integration test: rate limiting returns 429."""

from apps.api.src.middleware.rate_limit import RateLimiter


class TestRateLimitingIntegration:
    def test_burst_then_reject(self):
        limiter = RateLimiter(requests_per_minute=6, burst_size=3)
        results = [limiter.allow("t1") for _ in range(5)]
        allowed = [r[0] for r in results]
        assert allowed[:3] == [True, True, True]
        assert allowed[3] is False

    def test_429_response_shape(self):
        """Rate limit response should include retry_after > 0."""
        limiter = RateLimiter(requests_per_minute=6, burst_size=1)
        limiter.allow("t1")
        allowed, retry_after = limiter.allow("t1")
        assert allowed is False
        assert retry_after >= 1
