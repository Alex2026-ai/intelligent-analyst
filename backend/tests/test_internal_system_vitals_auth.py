"""
test_internal_system_vitals_auth.py — Day 6: Auth tests for /internal/system-vitals.

Uses dependency_overrides pattern from test_day5_versioning.py.
Enforces: no bypass, no API key fallback — Firebase admin claim only.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _make_mock_db():
    """Create a mock Firestore db that returns empty docs."""
    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_doc_ref = MagicMock()
    mock_doc_ref.get.return_value = mock_doc

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection
    return mock_db


def _admin_override():
    return {"role": "admin", "uid": "test-admin"}


class TestAdminGets200:
    def test_admin_200(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        mock_db = _make_mock_db()
        app.dependency_overrides[require_firebase_admin_claim] = _admin_override
        try:
            with patch("app.routes.internal_system_vitals._firestore_db", mock_db, create=True), \
                 patch("app.server_enterprise_golden._firestore_db", mock_db):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/internal/system-vitals")
            assert resp.status_code == 200
            data = resp.json()
            assert "finalize_p95_ms" in data
            assert "ledger_integrity" in data
        finally:
            app.dependency_overrides.pop(require_firebase_admin_claim, None)


class TestNonAdmin403:
    def test_non_admin_403(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        from fastapi import HTTPException

        async def _reject():
            raise HTTPException(status_code=403, detail="Admin role required")

        app.dependency_overrides[require_firebase_admin_claim] = _reject
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/internal/system-vitals")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_firebase_admin_claim, None)


class TestNoAuth401:
    def test_no_auth_401(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        from fastapi import HTTPException

        async def _no_auth():
            raise HTTPException(status_code=401, detail="Authorization header required")

        app.dependency_overrides[require_firebase_admin_claim] = _no_auth
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/internal/system-vitals")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(require_firebase_admin_claim, None)


class TestNoAuthRealFunction401:
    """Exercise the real require_firebase_admin_claim — no overrides, no bypass."""
    def test_no_header_returns_401(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        # Ensure NO overrides — real auth function runs
        app.dependency_overrides.pop(require_firebase_admin_claim, None)
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/internal/system-vitals")
            assert resp.status_code == 401
            assert "Authorization" in resp.json().get("detail", "")
        finally:
            pass

    def test_invalid_bearer_returns_401(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        app.dependency_overrides.pop(require_firebase_admin_claim, None)
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/internal/system-vitals",
                headers={"Authorization": "Bearer fake-token-xyz"}
            )
            # Either 401 (invalid token) or 503 (Firebase SDK not available in test)
            assert resp.status_code in (401, 503)
        finally:
            pass


class TestNoBypassExists:
    """Verify the auth function source has no bypass logic."""
    def test_no_allow_internal_bypass_in_source(self):
        import inspect
        from app.routes.internal_system_vitals import require_firebase_admin_claim
        source = inspect.getsource(require_firebase_admin_claim)
        assert "ALLOW_INTERNAL_BYPASS" not in source
        assert "bypass" not in source.lower()
        assert "local-bypass" not in source
        assert "local_bypass" not in source


class TestResponseSchema:
    def test_response_schema(self):
        from app.server_enterprise_golden import app
        from app.routes.internal_system_vitals import require_firebase_admin_claim

        mock_db = _make_mock_db()
        app.dependency_overrides[require_firebase_admin_claim] = _admin_override
        try:
            with patch("app.server_enterprise_golden._firestore_db", mock_db):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/internal/system-vitals")
            assert resp.status_code == 200
            data = resp.json()
            required_keys = [
                "finalize_p95_ms", "shard_p95_ms", "l3_cache_hit_rate",
                "failover_rate_percent", "ledger_integrity",
            ]
            for key in required_keys:
                assert key in data, f"Missing key: {key}"
        finally:
            app.dependency_overrides.pop(require_firebase_admin_claim, None)
