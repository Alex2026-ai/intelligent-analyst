"""Per-tenant, per-endpoint rate limiting.

Returns 429 Too Many Requests with Retry-After header when exceeded.
Limits configurable per tenant (INV-011: no silent thresholds).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _BucketState:
    """Token bucket state for a single tenant."""

    tokens: float = 0.0
    last_refill: float = 0.0


class RateLimiter:
    """In-memory token bucket rate limiter.

    Thread-safe. One bucket per tenant_id.
    """

    def __init__(self, requests_per_minute: int = 100, burst_size: int = 20) -> None:
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._burst = burst_size
        self._buckets: dict[str, _BucketState] = defaultdict(
            lambda: _BucketState(tokens=burst_size, last_refill=time.monotonic())
        )
        self._lock = Lock()

    def allow(self, tenant_id: str) -> tuple[bool, int]:
        """Check if a request from the given tenant is allowed.

        Args:
            tenant_id: Tenant making the request.

        Returns:
            (allowed, retry_after_seconds).
            retry_after_seconds is 0 if allowed.
        """
        with self._lock:
            bucket = self._buckets[tenant_id]
            now = time.monotonic()

            # Refill tokens
            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(self._burst, bucket.tokens + elapsed * self._rate)
            bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0
            else:
                # Calculate retry-after
                deficit = 1.0 - bucket.tokens
                retry_after = int(deficit / self._rate) + 1
                return False, retry_after
