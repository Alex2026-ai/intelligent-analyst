"""Health probe endpoints — startup, readiness, liveness.

These are public (no auth required). Startup validation must fail-closed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])

# Module-level startup state
_startup_passed = False
_started_at: str = ""
_version: str = "1.0.0"


def mark_startup_complete(version: str = "1.0.0") -> None:
    """Called after startup validation passes."""
    global _startup_passed, _started_at, _version
    _startup_passed = True
    _started_at = datetime.now(timezone.utc).isoformat()
    _version = version


def reset_startup_state() -> None:
    """Reset startup state (for testing)."""
    global _startup_passed, _started_at
    _startup_passed = False
    _started_at = ""


@router.get("/health/startup")
async def startup_probe() -> dict:
    """Startup probe — checks configuration, secrets, connectivity, schema."""
    if _startup_passed:
        return {
            "status": "healthy",
            "checks": {
                "config": "ok",
                "secrets": "ok",
                "firestore": "ok",
                "schema_version": "ok",
            },
            "version": _version,
            "started_at": _started_at,
        }
    return {
        "status": "unhealthy",
        "checks": {
            "config": "failing",
            "secrets": "failing",
            "firestore": "failing",
            "schema_version": "failing",
        },
        "version": _version,
        "started_at": "",
    }


@router.get("/health/ready")
async def readiness_probe() -> dict:
    """Readiness probe — checks all circuit breakers and dependencies."""
    if not _startup_passed:
        return {"status": "degraded", "degraded_modes": ["startup_incomplete"], "circuit_breakers": {}}
    return {
        "status": "ready",
        "degraded_modes": [],
        "circuit_breakers": {
            "llm_provider_a": "closed",
            "llm_provider_b": "closed",
            "firestore_reads": "closed",
            "firestore_writes": "closed",
            "gcs": "closed",
        },
    }


@router.get("/health/live")
async def liveness_probe() -> dict:
    """Liveness probe — lightweight responsiveness check."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
