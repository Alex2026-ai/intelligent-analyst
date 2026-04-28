"""Phase 2A: Backpressure Governor Tests.

Tests:
- Governor acquire/release lifecycle (finalize + shard)
- Global and per-tenant limits
- Finalize endpoint 202 on backpressure
- Release on success and error (finally clause)
"""

import os
import pytest
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# 1. BackpressureGovernor unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBackpressureGovernor:

    def setup_method(self):
        self._patches = [
            patch.dict(os.environ, {
                "MAX_CONCURRENT_FINALIZE_GLOBAL": "3",
                "MAX_CONCURRENT_FINALIZE_PER_TENANT": "1",
                "MAX_ACTIVE_SHARDS_GLOBAL": "50",
            }),
        ]
        for p in self._patches:
            p.start()
        from app.server_enterprise_golden import BackpressureGovernor
        self._cls = BackpressureGovernor

    def teardown_method(self):
        for p in reversed(self._patches):
            p.stop()

    def test_governor_allows_under_limit(self):
        gov = self._cls()
        ok, reason = gov.try_acquire_finalize("tenant-a")
        assert ok is True
        assert reason == "ok"

    def test_governor_blocks_at_global_limit(self):
        gov = self._cls()
        # Acquire 3 (global limit)
        for i in range(3):
            ok, _ = gov.try_acquire_finalize(f"tenant-{i}")
            assert ok is True
        # 4th should be blocked
        ok, reason = gov.try_acquire_finalize("tenant-extra")
        assert ok is False
        assert "global_finalize_limit" in reason

    def test_governor_blocks_at_tenant_limit(self):
        gov = self._cls()
        # Acquire 1 for tenant-a (per-tenant limit = 1)
        ok, _ = gov.try_acquire_finalize("tenant-a")
        assert ok is True
        # 2nd for same tenant should be blocked
        ok, reason = gov.try_acquire_finalize("tenant-a")
        assert ok is False
        assert "tenant_finalize_limit" in reason
        # Different tenant should be allowed
        ok, reason = gov.try_acquire_finalize("tenant-b")
        assert ok is True
        assert reason == "ok"

    def test_governor_release_frees_slot(self):
        gov = self._cls()
        # Fill up global limit
        for i in range(3):
            gov.try_acquire_finalize(f"tenant-{i}")
        # All full
        ok, _ = gov.try_acquire_finalize("tenant-new")
        assert ok is False
        # Release one
        gov.release_finalize("tenant-0")
        # Now should succeed
        ok, reason = gov.try_acquire_finalize("tenant-new")
        assert ok is True
        assert reason == "ok"

    def test_shard_governor_allows_under_limit(self):
        gov = self._cls()
        ok, reason = gov.try_acquire_shard()
        assert ok is True
        assert reason == "ok"

    def test_shard_governor_blocks_at_limit(self):
        gov = self._cls()
        # Acquire 50 (shard limit)
        for i in range(50):
            ok, _ = gov.try_acquire_shard()
            assert ok is True
        # 51st should be blocked
        ok, reason = gov.try_acquire_shard()
        assert ok is False
        assert "global_shard_limit" in reason

    def test_shard_release_frees_slot(self):
        gov = self._cls()
        for i in range(50):
            gov.try_acquire_shard()
        ok, _ = gov.try_acquire_shard()
        assert ok is False
        gov.release_shard()
        ok, reason = gov.try_acquire_shard()
        assert ok is True

    def test_snapshot_reflects_state(self):
        gov = self._cls()
        gov.try_acquire_finalize("tenant-a")
        gov.try_acquire_shard()
        gov.try_acquire_shard()
        snap = gov.snapshot()
        assert snap["active_finalize_global"] == 1
        assert snap["active_finalize_by_tenant"] == {"tenant-a": 1}
        assert snap["active_shards_global"] == 2

    def test_release_finalize_does_not_go_negative(self):
        gov = self._cls()
        gov.release_finalize("no-such-tenant")
        snap = gov.snapshot()
        assert snap["active_finalize_global"] == 0

    def test_release_shard_does_not_go_negative(self):
        gov = self._cls()
        gov.release_shard()
        snap = gov.snapshot()
        assert snap["active_shards_global"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Endpoint integration tests (backpressure behavior)
# ─────────────────────────────────────────────────────────────────────────────

def _bypass_transactional(func):
    def wrapper(transaction, *args, **kwargs):
        return func(transaction, *args, **kwargs)
    return wrapper


class TestFinalizeEndpointBackpressure:

    def _make_client(self, extra_patches=None):
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_finalize_endpoint_returns_202_on_backpressure(self):
        """When governor rejects, endpoint returns 202 queued."""
        mock_gov = MagicMock()
        mock_gov.try_acquire_finalize.return_value = (False, "global_finalize_limit (3/3)")
        patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._backpressure", mock_gov),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
        ]
        for p in patchers:
            p.start()
        try:
            client = self._make_client()
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": "BATCH-BP-TEST", "tenant_id": "tenant-bp",
            })
            assert resp.status_code == 202
            body = resp.json()
            assert body["status"] == "queued"
            assert "global_finalize_limit" in body["reason"]
            # Verify release was NOT called (we returned before try block)
            mock_gov.release_finalize.assert_not_called()
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_finalize_endpoint_releases_on_success(self):
        """After successful finalize, backpressure slot is released."""
        from tests.test_finalize_contract import InMemoryFirestore, _setup_db, VALID_RESULTS
        db = InMemoryFirestore()
        bid = "BATCH-BP-SUCCESS"
        _setup_db(db, bid, VALID_RESULTS)

        mock_gov = MagicMock()
        mock_gov.try_acquire_finalize.return_value = (True, "ok")
        mock_gov.snapshot.return_value = {"active_finalize_global": 0, "active_finalize_by_tenant": {}, "active_shards_global": 0}
        patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._firestore_db", db),
            patch("app.server_enterprise_golden._backpressure", mock_gov),
            patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
            patch("app.server_enterprise_golden.generate_and_store_evidence_blobs", MagicMock(return_value=(0, None))),
            patch("app.server_enterprise_golden.compute_and_store_hash_chain", MagicMock(return_value=(False, None))),
        ]
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 200
            mock_gov.release_finalize.assert_called_once_with("tenant-test")
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_finalize_endpoint_releases_on_error(self):
        """Even on finalize error, backpressure slot is released via finally."""
        from tests.test_finalize_contract import InMemoryFirestore, _setup_db, VALID_RESULTS
        db = InMemoryFirestore()
        bid = "BATCH-BP-ERROR"
        _setup_db(db, bid, VALID_RESULTS)

        mock_gov = MagicMock()
        mock_gov.try_acquire_finalize.return_value = (True, "ok")
        # Make fetch_sharded_results_deterministic raise to simulate error
        patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._firestore_db", db),
            patch("app.server_enterprise_golden._backpressure", mock_gov),
            patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
            patch("app.server_enterprise_golden.fetch_sharded_results_deterministic",
                  MagicMock(return_value=[])),
        ]
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            # Should fail (no results)
            assert resp.status_code == 500
            # But release must still be called (finally)
            mock_gov.release_finalize.assert_called_once_with("tenant-test")
        finally:
            for p in reversed(patchers):
                p.stop()
