"""
test_internal_endpoints_auth.py — Day 7 F4: Auth enforcement on internal Cloud Tasks endpoints.

Verifies that /internal/process-batch, /internal/process-shard, and
/internal/finalize-batch reject unauthenticated requests (fail-closed).
"""

import pytest
from fastapi.testclient import TestClient


class TestInternalProcessBatchAuth:
    """POST /internal/process-batch requires Bearer token."""

    def _post(self, headers=None):
        from app.server_enterprise_golden import app
        client = TestClient(app, raise_server_exceptions=False)
        return client.post("/internal/process-batch", headers=headers, json={
            "batch_trace_id": "BATCH-AUTH-TEST",
            "tenant_id": "tenant-test",
            "rows": ["Test Corp"],
            "filename": "test.csv",
        })

    def test_no_token_returns_401(self):
        resp = self._post()
        assert resp.status_code == 401, (
            f"Expected 401, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_invalid_bearer_returns_401(self):
        resp = self._post(headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401


class TestInternalProcessShardAuth:
    """POST /internal/process-shard requires Bearer token."""

    def _post(self, headers=None):
        from app.server_enterprise_golden import app
        client = TestClient(app, raise_server_exceptions=False)
        return client.post("/internal/process-shard", headers=headers, json={
            "batch_trace_id": "BATCH-AUTH-TEST",
            "tenant_id": "tenant-test",
            "shard_id": 0,
            "total_shards": 1,
            "rows": ["Test Corp"],
            "filename": "test.csv",
        })

    def test_no_token_returns_401(self):
        resp = self._post()
        assert resp.status_code == 401, (
            f"Expected 401, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_invalid_bearer_returns_401(self):
        resp = self._post(headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401


class TestInternalFinalizeBatchAuth:
    """POST /internal/finalize-batch requires Bearer token."""

    def _post(self, headers=None):
        from app.server_enterprise_golden import app
        client = TestClient(app, raise_server_exceptions=False)
        return client.post("/internal/finalize-batch", headers=headers, json={
            "batch_trace_id": "BATCH-AUTH-TEST",
            "tenant_id": "tenant-test",
        })

    def test_no_token_returns_401(self):
        resp = self._post()
        assert resp.status_code == 401, (
            f"Expected 401, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_invalid_bearer_returns_401(self):
        resp = self._post(headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401


class TestBypassRemovedFromSource:
    """Source inspection: ALLOW_INTERNAL_BYPASS must not exist anywhere."""

    def test_no_bypass_in_server_module(self):
        import inspect
        from app import server_enterprise_golden
        source = inspect.getsource(server_enterprise_golden)
        assert "ALLOW_INTERNAL_BYPASS" not in source, (
            "ALLOW_INTERNAL_BYPASS still present in server_enterprise_golden.py"
        )

    def test_no_bypass_in_verify_api_key(self):
        import inspect
        from app.server_enterprise_golden import verify_api_key
        source = inspect.getsource(verify_api_key)
        assert "ALLOW_INTERNAL_BYPASS" not in source
        assert "local_bypass" not in source

    def test_no_bypass_in_vitals_route(self):
        import inspect
        from app.routes.internal_system_vitals import require_firebase_admin_claim
        source = inspect.getsource(require_firebase_admin_claim)
        assert "ALLOW_INTERNAL_BYPASS" not in source
        assert "bypass" not in source.lower()
