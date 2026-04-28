"""Health check response models.

Models match GET /health/startup, GET /health/ready, and GET /health/live contracts exactly.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):
    """Overall health status."""

    HEALTHY = "healthy"
    READY = "ready"
    DEGRADED = "degraded"
    ALIVE = "alive"


class CheckStatus(str, Enum):
    """Status of an individual health check component."""

    OK = "ok"
    FAILING = "failing"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DegradedMode(str, Enum):
    """Known degraded mode identifiers."""

    LLM_DEGRADED = "llm_degraded"


class StartupChecks(BaseModel):
    """Component checks for the startup probe."""

    model_config = ConfigDict(strict=True)

    config: CheckStatus
    secrets: CheckStatus
    firestore: CheckStatus
    schema_version: CheckStatus


class StartupHealthResponse(BaseModel):
    """Response for GET /health/startup.

    Checks configuration, secrets, Firestore connectivity, and schema version.
    """

    model_config = ConfigDict(strict=True)

    status: HealthStatus
    checks: StartupChecks
    version: str = Field(..., description="Application version (semver)")
    started_at: str = Field(..., description="ISO 8601 timestamp")


class CircuitBreakers(BaseModel):
    """State of all circuit breakers for the readiness probe."""

    model_config = ConfigDict(strict=True)

    llm_provider_a: CircuitBreakerState
    llm_provider_b: CircuitBreakerState
    firestore_reads: CircuitBreakerState
    firestore_writes: CircuitBreakerState
    gcs: CircuitBreakerState


class ReadyHealthResponse(BaseModel):
    """Response for GET /health/ready.

    Checks all circuit breakers and dependencies.
    """

    model_config = ConfigDict(strict=True)

    status: HealthStatus
    degraded_modes: list[DegradedMode] = Field(default_factory=list)
    circuit_breakers: CircuitBreakers


class LiveHealthResponse(BaseModel):
    """Response for GET /health/live.

    Lightweight check that the process is responsive.
    """

    model_config = ConfigDict(strict=True)

    status: HealthStatus
    timestamp: str = Field(..., description="ISO 8601 timestamp")
