"""
================================================================================
INTELLIGENT ANALYST - TENANT RATE LIMITER (Days 21-30)
================================================================================

Enterprise-grade rate limiting with per-tenant quotas.

Features:
- 100 API requests/minute per tenant
- 5 concurrent batch uploads per tenant
- Redis-backed for distributed deployments
- Memory fallback for single-instance deployments
- Proper 429 responses with Retry-After header

Usage:
    from security.rate_limiter import TenantRateLimiter, rate_limit_middleware

    # FastAPI middleware
    app.middleware("http")(rate_limit_middleware)

    # Or manual check
    limiter = TenantRateLimiter()
    allowed, retry_after = await limiter.check_rate_limit(tenant_id, "api")

================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class RateLimitConfig:
    """Rate limit configuration per tenant."""

    # API request limits
    api_requests_per_minute: int = 100
    api_burst_size: int = 20  # Allow short bursts

    # Batch upload limits
    max_concurrent_uploads: int = 5
    upload_cooldown_seconds: int = 5  # Min time between uploads

    # Evidence pack downloads
    downloads_per_hour: int = 20

    # Global limits (across all tenants)
    global_requests_per_minute: int = 5000


# Default config
DEFAULT_CONFIG = RateLimitConfig()

# Per-tier configurations
TIER_CONFIGS: Dict[str, RateLimitConfig] = {
    "free": RateLimitConfig(
        api_requests_per_minute=30,
        max_concurrent_uploads=1,
        downloads_per_hour=5,
    ),
    "standard": RateLimitConfig(
        api_requests_per_minute=100,
        max_concurrent_uploads=5,
        downloads_per_hour=20,
    ),
    "enterprise": RateLimitConfig(
        api_requests_per_minute=500,
        max_concurrent_uploads=20,
        downloads_per_hour=100,
    ),
    "unlimited": RateLimitConfig(
        api_requests_per_minute=10000,
        max_concurrent_uploads=100,
        downloads_per_hour=1000,
    ),
}


# ============================================================================
# RATE LIMIT RESULT
# ============================================================================

@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    retry_after: int = 0  # Seconds until retry allowed
    remaining: int = 0  # Remaining requests in window
    limit: int = 0  # Total limit for window
    reset_at: float = 0.0  # Unix timestamp when window resets
    reason: str = ""  # Human-readable reason if blocked


# ============================================================================
# IN-MEMORY RATE LIMITER (Fallback)
# ============================================================================

class MemoryRateLimiter:
    """
    In-memory rate limiter using sliding window.

    Good for single-instance deployments or development.
    State is lost on restart.
    """

    def __init__(self):
        # Structure: {tenant_id: {bucket_key: [(timestamp, count), ...]}}
        self._windows: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._concurrent: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = asyncio.Lock()

    async def check_rate_limit(
        self,
        tenant_id: str,
        bucket: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check if request is allowed under rate limit."""
        async with self._lock:
            now = time.time()
            key = f"{tenant_id}:{bucket}"
            window_start = now - window_seconds

            # Get or create window
            if key not in self._windows[tenant_id]:
                self._windows[tenant_id][key] = []

            # Clean old entries
            self._windows[tenant_id][key] = [
                (ts, count) for ts, count in self._windows[tenant_id][key]
                if ts > window_start
            ]

            # Count requests in window
            current_count = sum(count for _, count in self._windows[tenant_id][key])

            if current_count >= limit:
                # Rate limited
                oldest = self._windows[tenant_id][key][0][0] if self._windows[tenant_id][key] else now
                retry_after = int(oldest + window_seconds - now) + 1
                return RateLimitResult(
                    allowed=False,
                    retry_after=max(1, retry_after),
                    remaining=0,
                    limit=limit,
                    reset_at=oldest + window_seconds,
                    reason=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
                )

            # Allow and record
            self._windows[tenant_id][key].append((now, 1))

            return RateLimitResult(
                allowed=True,
                remaining=limit - current_count - 1,
                limit=limit,
                reset_at=now + window_seconds,
            )

    async def acquire_concurrent(
        self,
        tenant_id: str,
        resource: str,
        max_concurrent: int,
    ) -> RateLimitResult:
        """Acquire a concurrent slot for a resource."""
        async with self._lock:
            key = f"{tenant_id}:{resource}"
            current = self._concurrent[tenant_id][key]

            if current >= max_concurrent:
                return RateLimitResult(
                    allowed=False,
                    retry_after=5,  # Suggest retry in 5s
                    remaining=0,
                    limit=max_concurrent,
                    reason=f"Max concurrent {resource} reached: {max_concurrent}",
                )

            self._concurrent[tenant_id][key] += 1
            return RateLimitResult(
                allowed=True,
                remaining=max_concurrent - current - 1,
                limit=max_concurrent,
            )

    async def release_concurrent(self, tenant_id: str, resource: str) -> None:
        """Release a concurrent slot."""
        async with self._lock:
            key = f"{tenant_id}:{resource}"
            if self._concurrent[tenant_id][key] > 0:
                self._concurrent[tenant_id][key] -= 1

    async def cleanup_old_entries(self, max_age_seconds: int = 3600) -> int:
        """Clean up old rate limit entries."""
        async with self._lock:
            now = time.time()
            cutoff = now - max_age_seconds
            cleaned = 0

            for tenant_id in list(self._windows.keys()):
                for key in list(self._windows[tenant_id].keys()):
                    old_len = len(self._windows[tenant_id][key])
                    self._windows[tenant_id][key] = [
                        (ts, count) for ts, count in self._windows[tenant_id][key]
                        if ts > cutoff
                    ]
                    cleaned += old_len - len(self._windows[tenant_id][key])

            return cleaned


# ============================================================================
# REDIS RATE LIMITER
# ============================================================================

class RedisRateLimiter:
    """
    Redis-backed rate limiter using sliding window log algorithm.

    Ideal for distributed deployments with multiple instances.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis = None
        self._initialized = False

    async def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                self._initialized = True
            except ImportError:
                logger.warning("redis-py not installed, falling back to memory limiter")
                return None
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, falling back to memory limiter")
                return None
        return self._redis

    async def check_rate_limit(
        self,
        tenant_id: str,
        bucket: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check rate limit using Redis sorted set."""
        redis = await self._get_redis()
        if redis is None:
            # Fallback - always allow but log
            logger.warning("Redis unavailable, allowing request")
            return RateLimitResult(allowed=True, remaining=limit, limit=limit)

        try:
            now = time.time()
            key = f"ratelimit:{tenant_id}:{bucket}"
            window_start = now - window_seconds

            # Use pipeline for atomic operations
            pipe = redis.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, "-inf", window_start)

            # Count current entries
            pipe.zcard(key)

            # Add new entry (if we'll allow it)
            pipe.zadd(key, {f"{now}": now})

            # Set expiry on key
            pipe.expire(key, window_seconds + 60)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                # Rate limited - remove the entry we just added
                await redis.zrem(key, f"{now}")

                # Get oldest entry to calculate retry time
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(oldest[0][1] + window_seconds - now) + 1
                else:
                    retry_after = window_seconds

                return RateLimitResult(
                    allowed=False,
                    retry_after=max(1, retry_after),
                    remaining=0,
                    limit=limit,
                    reset_at=now + retry_after,
                    reason=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
                )

            return RateLimitResult(
                allowed=True,
                remaining=limit - current_count - 1,
                limit=limit,
                reset_at=now + window_seconds,
            )

        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fail open - allow request
            return RateLimitResult(allowed=True, remaining=limit, limit=limit)

    async def acquire_concurrent(
        self,
        tenant_id: str,
        resource: str,
        max_concurrent: int,
    ) -> RateLimitResult:
        """Acquire concurrent slot using Redis."""
        redis = await self._get_redis()
        if redis is None:
            return RateLimitResult(allowed=True, remaining=max_concurrent, limit=max_concurrent)

        try:
            key = f"concurrent:{tenant_id}:{resource}"

            # Use INCR with conditional logic
            current = await redis.incr(key)

            if current > max_concurrent:
                # Over limit - decrement and reject
                await redis.decr(key)
                return RateLimitResult(
                    allowed=False,
                    retry_after=5,
                    remaining=0,
                    limit=max_concurrent,
                    reason=f"Max concurrent {resource} reached: {max_concurrent}",
                )

            # Set expiry (safety - in case release is never called)
            await redis.expire(key, 3600)  # 1 hour max

            return RateLimitResult(
                allowed=True,
                remaining=max_concurrent - current,
                limit=max_concurrent,
            )

        except Exception as e:
            logger.error(f"Redis concurrent acquire failed: {e}")
            return RateLimitResult(allowed=True, remaining=max_concurrent, limit=max_concurrent)

    async def release_concurrent(self, tenant_id: str, resource: str) -> None:
        """Release concurrent slot."""
        redis = await self._get_redis()
        if redis is None:
            return

        try:
            key = f"concurrent:{tenant_id}:{resource}"
            current = await redis.decr(key)

            # Don't go negative
            if current < 0:
                await redis.set(key, 0)

        except Exception as e:
            logger.error(f"Redis concurrent release failed: {e}")


# ============================================================================
# TENANT RATE LIMITER (Main Interface)
# ============================================================================

class TenantRateLimiter:
    """
    Main rate limiter interface.

    Automatically chooses Redis or memory backend.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._backend: Optional[Any] = None
        self._tenant_tiers: Dict[str, str] = {}

    def _get_backend(self):
        """Get or create the backend."""
        if self._backend is None:
            if self._redis_url:
                self._backend = RedisRateLimiter(self._redis_url)
                logger.info("Using Redis rate limiter")
            else:
                self._backend = MemoryRateLimiter()
                logger.info("Using in-memory rate limiter")
        return self._backend

    def get_config(self, tenant_id: str) -> RateLimitConfig:
        """Get rate limit config for tenant."""
        tier = self._tenant_tiers.get(tenant_id, "standard")
        return TIER_CONFIGS.get(tier, DEFAULT_CONFIG)

    def set_tenant_tier(self, tenant_id: str, tier: str) -> None:
        """Set the tier for a tenant."""
        if tier in TIER_CONFIGS:
            self._tenant_tiers[tenant_id] = tier

    async def check_api_limit(self, tenant_id: str) -> RateLimitResult:
        """Check API request rate limit."""
        config = self.get_config(tenant_id)
        backend = self._get_backend()

        return await backend.check_rate_limit(
            tenant_id=tenant_id,
            bucket="api",
            limit=config.api_requests_per_minute,
            window_seconds=60,
        )

    async def check_upload_limit(self, tenant_id: str) -> RateLimitResult:
        """Check if upload is allowed (concurrent limit)."""
        config = self.get_config(tenant_id)
        backend = self._get_backend()

        return await backend.acquire_concurrent(
            tenant_id=tenant_id,
            resource="uploads",
            max_concurrent=config.max_concurrent_uploads,
        )

    async def release_upload_slot(self, tenant_id: str) -> None:
        """Release an upload slot after completion."""
        backend = self._get_backend()
        await backend.release_concurrent(tenant_id, "uploads")

    async def check_download_limit(self, tenant_id: str) -> RateLimitResult:
        """Check download rate limit (per hour)."""
        config = self.get_config(tenant_id)
        backend = self._get_backend()

        return await backend.check_rate_limit(
            tenant_id=tenant_id,
            bucket="downloads",
            limit=config.downloads_per_hour,
            window_seconds=3600,
        )


# ============================================================================
# GLOBAL LIMITER INSTANCE
# ============================================================================

_global_limiter: Optional[TenantRateLimiter] = None


def get_rate_limiter() -> TenantRateLimiter:
    """Get the global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = TenantRateLimiter()
    return _global_limiter


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

# Paths exempt from rate limiting
EXEMPT_PATHS = {
    "/health",
    "/healthz",
    "/ready",
    "/metrics",
    "/",
}

# Paths with stricter limits (batch uploads)
UPLOAD_PATHS = {
    "/api/batch-upload",
    "/api/batches",
}

# Paths for downloads
DOWNLOAD_PATHS = {
    "/evidence-pack",
    "/export",
    "/certificate",
}


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """
    FastAPI middleware for rate limiting.

    Returns 429 Too Many Requests with Retry-After header when limit exceeded.
    """
    path = request.url.path

    # Skip exempt paths
    if path in EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
        return await call_next(request)

    # Extract tenant ID from auth context or header
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        # Try to get from auth (set by auth middleware)
        auth = getattr(request.state, "auth", None)
        if auth:
            tenant_id = auth.get("tenant_id")

    if not tenant_id:
        # No tenant context - use IP-based limiting
        tenant_id = f"ip:{request.client.host}" if request.client else "unknown"

    limiter = get_rate_limiter()

    # Check for upload paths (concurrent limit)
    is_upload = any(up in path for up in UPLOAD_PATHS) and request.method == "POST"
    if is_upload:
        result = await limiter.check_upload_limit(tenant_id)
        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": result.reason,
                    "retry_after": result.retry_after,
                    "limit": result.limit,
                    "remaining": result.remaining,
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )

        # Process request and release slot after
        try:
            response = await call_next(request)
        finally:
            await limiter.release_upload_slot(tenant_id)
        return response

    # Check for download paths (hourly limit)
    is_download = any(dp in path for dp in DOWNLOAD_PATHS) and request.method == "GET"
    if is_download:
        result = await limiter.check_download_limit(tenant_id)
        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": result.reason,
                    "retry_after": result.retry_after,
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )

    # Standard API rate limit
    result = await limiter.check_api_limit(tenant_id)
    if not result.allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "detail": result.reason,
                "retry_after": result.retry_after,
            },
            headers={
                "Retry-After": str(result.retry_after),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at)),
            },
        )

    # Add rate limit headers to successful responses
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)

    return response


# ============================================================================
# FASTAPI DEPENDENCY
# ============================================================================

async def check_rate_limit(request: Request) -> RateLimitResult:
    """
    FastAPI dependency for rate limiting.

    Usage:
        @app.get("/endpoint")
        async def endpoint(rate_limit: RateLimitResult = Depends(check_rate_limit)):
            if not rate_limit.allowed:
                raise HTTPException(429, detail=rate_limit.reason)
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        auth = getattr(request.state, "auth", None)
        if auth:
            tenant_id = auth.get("tenant_id")

    if not tenant_id:
        tenant_id = f"ip:{request.client.host}" if request.client else "unknown"

    limiter = get_rate_limiter()
    return await limiter.check_api_limit(tenant_id)


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_limiter():
        limiter = TenantRateLimiter()

        print("Testing rate limiter...")

        # Test API limits
        for i in range(105):
            result = await limiter.check_api_limit("test-tenant")
            if not result.allowed:
                print(f"Blocked at request {i+1}: {result.reason}")
                print(f"Retry after: {result.retry_after}s")
                break
            else:
                if (i + 1) % 20 == 0:
                    print(f"Request {i+1}: OK (remaining: {result.remaining})")

        print()

        # Test concurrent uploads
        print("Testing concurrent uploads...")
        slots = []
        for i in range(7):
            result = await limiter.check_upload_limit("test-tenant")
            if result.allowed:
                slots.append(i)
                print(f"Upload {i+1}: Acquired (remaining: {result.remaining})")
            else:
                print(f"Upload {i+1}: Blocked - {result.reason}")

        # Release slots
        for slot in slots:
            await limiter.release_upload_slot("test-tenant")
            print(f"Released upload slot {slot+1}")

    asyncio.run(test_limiter())
