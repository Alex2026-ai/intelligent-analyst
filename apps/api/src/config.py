"""Application configuration — loaded from environment variables.

All secrets should come from Secret Manager in production.
No secrets hardcoded here (FP-004).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CORSConfig:
    """CORS configuration — never '*' (FP-003)."""

    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    allowed_methods: list[str] = field(default_factory=lambda: ["GET", "POST", "OPTIONS"])
    allowed_headers: list[str] = field(
        default_factory=lambda: ["Authorization", "Content-Type", "Idempotency-Key", "X-Tenant-Id"]
    )


@dataclass(frozen=True)
class RateLimitConfig:
    """Per-tenant rate limit defaults."""

    requests_per_minute: int = 100
    burst_size: int = 20


@dataclass(frozen=True)
class AppSettings:
    """Top-level application settings."""

    service_name: str = "ia-api"
    version: str = "1.0.0"
    environment: str = "development"

    # Auth / token validation
    auth_provider: str = "jwks"  # "jwks" or "firebase"
    jwks_url: str = ""
    jwks_cache_ttl_seconds: int = 300
    auth_audience: str = ""
    auth_issuer: str = ""

    # CORS (FP-003: never '*')
    cors: CORSConfig = field(default_factory=CORSConfig)

    # Rate limiting
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Schema
    expected_schema_version: str = "1.0"

    # Firestore
    firestore_project: str = ""

    @property
    def cors_origins_valid(self) -> bool:
        """Verify CORS is not open (FP-003)."""
        return "*" not in self.cors.allowed_origins

    @classmethod
    def from_env(cls) -> AppSettings:
        """Load settings from environment variables."""
        import os
        return cls(
            environment=os.environ.get("ENVIRONMENT", "development"),
            auth_provider=os.environ.get("AUTH_PROVIDER", "jwks"),
            jwks_url=os.environ.get("JWKS_URL", ""),
            jwks_cache_ttl_seconds=int(os.environ.get("JWKS_CACHE_TTL", "300")),
            auth_audience=os.environ.get("AUTH_AUDIENCE", ""),
            auth_issuer=os.environ.get("AUTH_ISSUER", ""),
            firestore_project=os.environ.get("FIRESTORE_PROJECT", ""),
        )
