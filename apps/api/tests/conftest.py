"""Shared test fixtures for API tests."""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Force test mode — in-memory backends for all tests
os.environ["TESTING"] = "true"

from apps.api.src.config import AppSettings
from apps.api.src.main import create_app
from apps.api.src.middleware.auth import TokenValidator
from apps.api.src.routes.health import mark_startup_complete, reset_startup_state


def _make_claims(
    sub: str = "user-1",
    tenant_id: str = "tenant-1",
    role: str = "analyst",
    exp: float | None = None,
) -> dict[str, Any]:
    """Create JWT-like claims for testing."""
    claims = {"sub": sub, "tenant_id": tenant_id, "role": role}
    if exp is not None:
        claims["exp"] = exp
    else:
        claims["exp"] = time.time() + 3600  # 1 hour from now
    return claims


# Token constants for convenience
VALID_TOKEN = "valid-analyst-token"
REVIEWER_TOKEN = "valid-reviewer-token"
ADMIN_TOKEN = "valid-admin-token"
PLATFORM_ADMIN_TOKEN = "valid-platform-admin-token"
EXPIRED_TOKEN = "expired-token"
INVALID_TOKEN = "invalid-token"
MISSING_CLAIMS_TOKEN = "missing-claims-token"
TENANT_B_TOKEN = "tenant-b-token"

TOKEN_MAP: dict[str, dict[str, Any] | None] = {
    VALID_TOKEN: _make_claims(role="analyst"),
    REVIEWER_TOKEN: _make_claims(role="reviewer"),
    ADMIN_TOKEN: _make_claims(role="tenant_admin"),
    PLATFORM_ADMIN_TOKEN: _make_claims(role="platform_admin"),
    EXPIRED_TOKEN: _make_claims(exp=time.time() - 3600),  # Expired 1h ago
    INVALID_TOKEN: None,  # Signature invalid
    MISSING_CLAIMS_TOKEN: {"sub": "user-1"},  # Missing tenant_id, role
    TENANT_B_TOKEN: _make_claims(tenant_id="tenant-B", role="analyst"),
}


def _test_verify(token: str) -> dict[str, Any] | None:
    """Test token verifier that uses the TOKEN_MAP."""
    return TOKEN_MAP.get(token)


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    settings = AppSettings()
    validator = TokenValidator(verify_func=_test_verify)
    test_app = create_app(settings=settings, token_validator=validator)
    mark_startup_complete("1.0.0")
    yield test_app
    reset_startup_state()


@pytest.fixture
def client(app) -> TestClient:
    """Create a test client."""
    return TestClient(app)


def auth_header(token: str = VALID_TOKEN) -> dict[str, str]:
    """Create an Authorization header."""
    return {"Authorization": f"Bearer {token}"}
