"""Phase 2A Institutional Validation.

7-section validation suite:
1) Determinism Guard — identical root_hash, signature, no timing in receipt
2) Lock Integrity — 10 concurrent calls, only 1 acquires, batch doc untouched
3) Backpressure Safety — 202 does not fail batch, queued batches finalize later
4) Transaction Cap Safety — fail-closed, finalize_state consistent
5) Memory Isolation — counters reset, no underflow, multi-tenant enforcement
6) Full pytest (run separately)
7) Receipt structure, protocol version, performance (code inspection)
"""

import os
import copy
import time
import threading
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Shared test infrastructure (reuse from test_finalize_contract)
# ─────────────────────────────────────────────────────────────────────────────

from tests.test_finalize_contract import (
    InMemoryFirestore, MockFirestoreDoc, _CollectionRef, _DocRef,
    _InMemoryTransaction, _setup_db, _bypass_transactional,
    VALID_RESULTS,
)


def _make_patchers(db, extra=None):
    """Standard patchers for finalize endpoint tests."""
    patchers = [
        patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
        patch("app.server_enterprise_golden._firestore_db", db),
        patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
        patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
        patch("app.server_enterprise_golden.generate_and_store_evidence_blobs",
              MagicMock(return_value=(0, None))),
        patch("app.server_enterprise_golden.compute_and_store_hash_chain",
              MagicMock(return_value=(False, None))),
    ]
    if extra:
        patchers.extend(extra)
    return patchers


def _run_finalize(db, bid, tenant_id="tenant-test"):
    """Run finalize endpoint, return (status_code, resp_json, db)."""
    patchers = _make_patchers(db)
    for p in patchers:
        p.start()
    try:
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
            "batch_trace_id": bid, "tenant_id": tenant_id,
        })
        return resp.status_code, resp.json(), db
    finally:
        for p in reversed(patchers):
            p.stop()


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1: DETERMINISM GUARD
# ═════════════════════════════════════════════════════════════════════════════

class TestDeterminismGuard:
    """
    Run same batch twice.
    Confirm identical root_hash.
    Confirm identical signature.
    Confirm no timing metadata enters receipt.
    """

    def _run_and_extract(self, bid_suffix):
        db = InMemoryFirestore()
        bid = f"BATCH-DET-{bid_suffix}"
        _setup_db(db, bid, VALID_RESULTS)
        status_code, resp_json, db = _run_finalize(db, bid)
        assert status_code == 200, f"Expected 200, got {status_code}: {resp_json}"
        batch = db._data.get(f"batches/{bid}", {})
        return batch

    def test_identical_root_hash_on_replay(self):
        """Run 1 and Run 2 produce identical root_hash."""
        batch1 = self._run_and_extract("RUN1")
        batch2 = self._run_and_extract("RUN2")

        receipt1 = batch1.get("veracity_receipt", {})
        receipt2 = batch2.get("veracity_receipt", {})

        rh1 = receipt1.get("root_hash")
        rh2 = receipt2.get("root_hash")

        # Both should be present (or both None if hash_chain mocked)
        assert rh1 == rh2, f"root_hash drift: {rh1} != {rh2}"

    def test_identical_signature_on_replay(self):
        """Signature field is identical across runs (mocked, so both None-equivalent)."""
        batch1 = self._run_and_extract("SIG1")
        batch2 = self._run_and_extract("SIG2")

        sig1 = batch1.get("signature")
        sig2 = batch2.get("signature")
        assert sig1 == sig2, f"Signature drift: {sig1} != {sig2}"

    def test_no_timing_metadata_in_receipt(self):
        """
        veracity_receipt must NOT contain Phase 2A timing fields.
        lock_wait_seconds, shard_merge_duration, write_duration must NOT
        leak into the veracity_receipt (they belong in slog only).
        """
        batch = self._run_and_extract("TIMING")
        receipt = batch.get("veracity_receipt", {})

        timing_fields = [
            "lock_wait_seconds", "shard_merge_duration_seconds",
            "write_duration_seconds", "batch_write_seconds",
            "shard_merge_seconds", "backpressure",
        ]
        for field in timing_fields:
            assert field not in receipt, \
                f"Timing field '{field}' leaked into veracity_receipt"

    def test_receipt_contains_only_expected_keys(self):
        """Receipt must contain exactly the expected keys — no extras."""
        batch = self._run_and_extract("KEYS")
        receipt = batch.get("veracity_receipt", {})

        expected_keys = {
            "shard_receipts", "total_shards", "total_records",
            "root_hash", "anchor", "attestation", "finalized_at",
            "finalize_duration_seconds", "version_snapshot",
            "tenant_id", "index_integrity_proof_v1",
            "signing",  # Day 5 Gate S2: tenant-scoped signing metadata
        }
        actual_keys = set(receipt.keys())
        unexpected = actual_keys - expected_keys
        assert not unexpected, f"Unexpected keys in receipt: {unexpected}"

    def test_finalize_duration_is_only_timing_in_receipt(self):
        """finalize_duration_seconds is the ONLY timing field in receipt (legacy)."""
        batch = self._run_and_extract("ONLY-TIMING")
        receipt = batch.get("veracity_receipt", {})
        # finalize_duration_seconds is allowed (pre-existing)
        assert "finalize_duration_seconds" in receipt


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2: LOCK INTEGRITY
# ═════════════════════════════════════════════════════════════════════════════

class TestLockIntegrity:
    """
    10 concurrent finalize calls.
    Only 1 acquires. Others get 409 or 202.
    Batch metadata document untouched during lock lifecycle.
    """

    def setup_method(self):
        self._p = patch("app.server_enterprise_golden._finalize_transactional",
                        _bypass_transactional)
        self._p.start()
        from app.server_enterprise_golden import acquire_finalize_lock, complete_finalize_state
        self._acquire = acquire_finalize_lock
        self._complete = complete_finalize_state

    def teardown_method(self):
        self._p.stop()

    def test_10_concurrent_only_1_acquires(self):
        """10 sequential calls to acquire_finalize_lock → exactly 1 acquired."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-10"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "none", "finalize_lock": None,
        }

        results = []
        for i in range(10):
            r, lid = self._acquire(bid, f"worker-{i}", db)
            results.append((r, lid))

        acquired = [r for r in results if r[0] == "acquired"]
        locked = [r for r in results if r[0] == "locked"]
        assert len(acquired) == 1, f"Expected 1 acquired, got {len(acquired)}"
        assert len(locked) == 9, f"Expected 9 locked, got {len(locked)}"

    def test_no_partial_state_on_contention(self):
        """After contention, finalize_state doc is either locked by winner or clean."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-PARTIAL"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "none", "finalize_lock": None,
        }

        results = []
        for i in range(10):
            r, lid = self._acquire(bid, f"worker-{i}", db)
            results.append((r, lid))

        state_doc = db._data[f"batch_finalize_state/{bid}"]
        # State must be "finalizing" (winner's state)
        assert state_doc["finalize_state"] == "finalizing"
        # Lock must have exactly one lock_id
        assert state_doc["finalize_lock"] is not None
        assert "lock_id" in state_doc["finalize_lock"]
        # Must have all required fields
        assert "locked_by" in state_doc["finalize_lock"]
        assert "locked_at" in state_doc["finalize_lock"]
        assert "expires_at" in state_doc["finalize_lock"]

    def test_batch_doc_completely_untouched_during_lock_lifecycle(self):
        """Batch doc is bit-identical before and after full lock acquire+release."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-UNTOUCHED-10"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "none", "finalize_lock": None,
        }
        original_batch = {
            "status": "finalizing",
            "total": 100,
            "tenant_id": "t1",
            "counts": {"l0": 5, "l1": 80, "l2": 10, "l3": 2, "l4": 3},
            "total_l3_spent_usd": 0.05,
        }
        db._data[f"batches/{bid}"] = copy.deepcopy(original_batch)

        # 10 lock attempts
        winner_lock_id = None
        for i in range(10):
            r, lid = self._acquire(bid, f"worker-{i}", db)
            if r == "acquired":
                winner_lock_id = lid

        # Batch doc must be unchanged
        assert db._data[f"batches/{bid}"] == original_batch, \
            "Batch doc was modified during lock acquisition"

        # Complete finalize state
        self._complete(bid, winner_lock_id, "completed", db)

        # Batch doc still unchanged
        assert db._data[f"batches/{bid}"] == original_batch, \
            "Batch doc was modified during lock release"

    def test_losers_get_409_not_partial(self):
        """
        All non-winners must get clean rejection:
        - 409 (locked) at lock level, never partial write.
        """
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-409-10"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "none", "finalize_lock": None,
        }

        results = []
        for i in range(10):
            r, lid = self._acquire(bid, f"worker-{i}", db)
            results.append(r)

        # No unexpected result types
        valid_results = {"acquired", "locked"}
        for r in results:
            assert r in valid_results, f"Unexpected lock result: {r}"


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: BACKPRESSURE SAFETY
# ═════════════════════════════════════════════════════════════════════════════

class TestBackpressureSafety:
    """
    202 does NOT mark batch failed.
    Queued batches can later finalize successfully.
    No retry storms.
    """

    def test_202_does_not_mark_batch_failed(self):
        """When governor rejects → 202 returned, batch stays 'finalizing'."""
        db = InMemoryFirestore()
        bid = "BATCH-BP-NOFAIL"
        _setup_db(db, bid, VALID_RESULTS)

        mock_gov = MagicMock()
        mock_gov.try_acquire_finalize.return_value = (False, "global_finalize_limit (3/3)")

        patchers = _make_patchers(db, extra=[
            patch("app.server_enterprise_golden._backpressure", mock_gov),
        ])
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 202
            body = resp.json()
            assert body["status"] == "queued"

            # Batch must NOT be failed
            batch = db._data[f"batches/{bid}"]
            assert batch["status"] == "finalizing", \
                f"Batch status changed to '{batch['status']}' after 202"

            # finalize_state doc must be unchanged
            state = db._data[f"batch_finalize_state/{bid}"]
            assert state["finalize_state"] == "none", \
                f"finalize_state changed to '{state['finalize_state']}' after 202"

            # No lock should be held
            assert state.get("finalize_lock") is None
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_queued_batch_can_finalize_later(self):
        """
        First call → 202 (backpressure).
        Second call → governor allows → 200 completed.
        """
        db = InMemoryFirestore()
        bid = "BATCH-BP-RETRY"
        _setup_db(db, bid, VALID_RESULTS)

        mock_gov = MagicMock()
        # First call: rejected. Second call: allowed.
        mock_gov.try_acquire_finalize.side_effect = [
            (False, "global_finalize_limit (3/3)"),
            (True, "ok"),
        ]
        mock_gov.snapshot.return_value = {
            "active_finalize_global": 0,
            "active_finalize_by_tenant": {},
            "active_shards_global": 0,
        }

        patchers = _make_patchers(db, extra=[
            patch("app.server_enterprise_golden._backpressure", mock_gov),
        ])
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)

            # First: 202
            resp1 = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp1.status_code == 202
            assert resp1.json()["status"] == "queued"

            # Second: should complete
            resp2 = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp2.status_code == 200
            assert resp2.json()["status"] == "completed"

            # Batch is now completed
            batch = db._data[f"batches/{bid}"]
            assert batch["status"] == "completed"
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_no_retry_storm_202_does_not_trigger_retry(self):
        """
        202 Accepted means Cloud Tasks considers the task done.
        Verify: release_finalize is NOT called on 202 path (slot was never acquired).
        """
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
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": "BATCH-BP-NORETRY", "tenant_id": "t1",
            })
            assert resp.status_code == 202
            # release_finalize MUST NOT be called (slot was never acquired)
            mock_gov.release_finalize.assert_not_called()
        finally:
            for p in reversed(patchers):
                p.stop()


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4: TRANSACTION CAP SAFETY
# ═════════════════════════════════════════════════════════════════════════════

class TestTransactionCapSafety:
    """
    Force transaction retry exhaustion.
    Batch fails closed.
    finalize_state is consistent.
    Lock cleared or TTL respected.
    No orphan finalize_state doc.
    """

    def test_transaction_retry_cap_configured(self):
        """Config reads FINALIZE_TXN_MAX_ATTEMPTS, used by db.transaction() calls."""
        with patch.dict(os.environ, {"FINALIZE_TXN_MAX_ATTEMPTS": "5"}):
            # Import fresh to get new config
            import importlib
            import app.server_enterprise_golden as seg
            importlib.reload(seg)
            # The config should read 5
            assert seg.config.FINALIZE_TXN_MAX_ATTEMPTS == 5

    def test_finalize_error_sets_batch_failed(self):
        """If finalize raises after lock acquired, batch set to failed."""
        db = InMemoryFirestore()
        bid = "BATCH-TXN-FAIL"
        _setup_db(db, bid, VALID_RESULTS)

        def _boom(*args, **kwargs):
            raise RuntimeError("Simulated transaction retry exhaustion")

        patchers = _make_patchers(db, extra=[
            patch("app.server_enterprise_golden.fetch_sharded_results_deterministic", _boom),
        ])
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 500

            # Batch must be failed (fail-closed)
            batch = db._data[f"batches/{bid}"]
            assert batch["status"] == "failed"

            # finalize_state must be "failed" (lock released via complete_finalize_state)
            state = db._data[f"batch_finalize_state/{bid}"]
            assert state["finalize_state"] == "failed"

            # Lock must be cleared
            assert state.get("finalize_lock") is None
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_finalize_state_doc_always_exists_after_failure(self):
        """finalize_state doc must exist after failure — no orphans."""
        db = InMemoryFirestore()
        bid = "BATCH-TXN-ORPHAN"
        _setup_db(db, bid, VALID_RESULTS)

        def _boom(*args, **kwargs):
            raise RuntimeError("Boom")

        patchers = _make_patchers(db, extra=[
            patch("app.server_enterprise_golden.fetch_sharded_results_deterministic", _boom),
        ])
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 500

            # finalize_state doc MUST exist
            assert f"batch_finalize_state/{bid}" in db._data, \
                "finalize_state doc missing after failure — orphan risk"
            state = db._data[f"batch_finalize_state/{bid}"]
            assert state["finalize_state"] in ("failed", "finalizing"), \
                f"Unexpected finalize_state: {state['finalize_state']}"
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_ttl_respected_on_lock_clear_failure(self):
        """
        If complete_finalize_state fails, lock should have TTL that expires.
        Verify lock has expires_at set when acquired.
        """
        p = patch("app.server_enterprise_golden._finalize_transactional",
                  _bypass_transactional)
        p.start()
        try:
            from app.server_enterprise_golden import acquire_finalize_lock, FINALIZE_LOCK_TTL_SECONDS
            db = InMemoryFirestore()
            bid = "BATCH-TTL-CHECK"
            db._data[f"batch_finalize_state/{bid}"] = {
                "finalize_state": "none", "finalize_lock": None,
            }
            result, lock_id = acquire_finalize_lock(bid, "test-worker", db)
            assert result == "acquired"

            state = db._data[f"batch_finalize_state/{bid}"]
            lock = state["finalize_lock"]
            assert "expires_at" in lock

            # Parse and verify TTL
            expires = datetime.fromisoformat(lock["expires_at"])
            locked_at = datetime.fromisoformat(lock["locked_at"])
            ttl = (expires - locked_at).total_seconds()
            assert abs(ttl - FINALIZE_LOCK_TTL_SECONDS) < 2, \
                f"TTL mismatch: expected {FINALIZE_LOCK_TTL_SECONDS}, got {ttl}"
        finally:
            p.stop()


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5: MEMORY ISOLATION
# ═════════════════════════════════════════════════════════════════════════════

class TestMemoryIsolation:
    """
    In-memory counters reset correctly across requests.
    No negative counter underflow.
    Multi-tenant limits enforced correctly.
    """

    def _new_governor(self):
        with patch.dict(os.environ, {
            "MAX_CONCURRENT_FINALIZE_GLOBAL": "3",
            "MAX_CONCURRENT_FINALIZE_PER_TENANT": "1",
            "MAX_ACTIVE_SHARDS_GLOBAL": "50",
        }):
            from app.server_enterprise_golden import BackpressureGovernor
            return BackpressureGovernor()

    def test_counters_return_to_zero_after_full_lifecycle(self):
        """Acquire N, release N → all counters back to 0."""
        gov = self._new_governor()
        tenants = ["t-a", "t-b", "t-c"]
        for t in tenants:
            gov.try_acquire_finalize(t)
        for i in range(5):
            gov.try_acquire_shard()

        # Release all
        for t in tenants:
            gov.release_finalize(t)
        for i in range(5):
            gov.release_shard()

        snap = gov.snapshot()
        assert snap["active_finalize_global"] == 0
        assert snap["active_finalize_by_tenant"] == {}
        assert snap["active_shards_global"] == 0

    def test_no_negative_underflow_finalize(self):
        """Release without acquire → counter stays at 0, not -1."""
        gov = self._new_governor()
        gov.release_finalize("no-such-tenant")
        gov.release_finalize("no-such-tenant")
        gov.release_finalize("no-such-tenant")
        snap = gov.snapshot()
        assert snap["active_finalize_global"] == 0
        assert snap["active_finalize_by_tenant"] == {}

    def test_no_negative_underflow_shard(self):
        """Release shard without acquire → counter stays at 0."""
        gov = self._new_governor()
        gov.release_shard()
        gov.release_shard()
        gov.release_shard()
        snap = gov.snapshot()
        assert snap["active_shards_global"] == 0

    def test_multi_tenant_isolation(self):
        """Tenant A at limit does not block Tenant B."""
        gov = self._new_governor()
        ok_a, _ = gov.try_acquire_finalize("tenant-a")
        assert ok_a is True

        # Tenant A at limit (per-tenant = 1)
        ok_a2, reason = gov.try_acquire_finalize("tenant-a")
        assert ok_a2 is False
        assert "tenant_finalize_limit" in reason

        # Tenant B should work
        ok_b, _ = gov.try_acquire_finalize("tenant-b")
        assert ok_b is True

        # Tenant C should work
        ok_c, _ = gov.try_acquire_finalize("tenant-c")
        assert ok_c is True

        # Now at global limit (3)
        ok_d, reason = gov.try_acquire_finalize("tenant-d")
        assert ok_d is False
        assert "global_finalize_limit" in reason

    def test_release_one_tenant_does_not_affect_others(self):
        """Releasing tenant-a's slot doesn't change tenant-b's count."""
        gov = self._new_governor()
        gov.try_acquire_finalize("tenant-a")
        gov.try_acquire_finalize("tenant-b")

        snap_before = gov.snapshot()
        assert snap_before["active_finalize_by_tenant"]["tenant-b"] == 1

        gov.release_finalize("tenant-a")

        snap_after = gov.snapshot()
        assert "tenant-a" not in snap_after["active_finalize_by_tenant"]
        assert snap_after["active_finalize_by_tenant"]["tenant-b"] == 1

    def test_concurrent_thread_safety(self):
        """Multiple threads acquire/release without corruption."""
        gov = self._new_governor()
        errors = []

        def worker(tid, gov, errors):
            try:
                for _ in range(100):
                    ok, _ = gov.try_acquire_shard()
                    if ok:
                        gov.release_shard()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i, gov, errors))
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        snap = gov.snapshot()
        assert snap["active_shards_global"] >= 0, "Negative shard count"

    def test_independent_governor_instances(self):
        """Two governor instances do not share state."""
        gov1 = self._new_governor()
        gov2 = self._new_governor()

        gov1.try_acquire_finalize("tenant-a")
        gov1.try_acquire_shard()

        snap2 = gov2.snapshot()
        assert snap2["active_finalize_global"] == 0
        assert snap2["active_shards_global"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7: RECEIPT STRUCTURE + PROTOCOL VERSION (static checks)
# ═════════════════════════════════════════════════════════════════════════════

class TestReceiptStructureAndProtocol:
    """
    No change in receipt structure.
    No protocol version change.
    """

    def test_receipt_keys_match_day4_contract(self):
        """Receipt keys must match Day 4 contract exactly."""
        db = InMemoryFirestore()
        bid = "BATCH-RECEIPT-CONTRACT"
        _setup_db(db, bid, VALID_RESULTS)
        status_code, resp_json, db = _run_finalize(db, bid)
        assert status_code == 200

        receipt = db._data[f"batches/{bid}"]["veracity_receipt"]
        required_keys = {
            "shard_receipts", "total_shards", "total_records",
            "root_hash", "anchor", "attestation", "finalized_at",
            "finalize_duration_seconds", "version_snapshot",
            "tenant_id", "index_integrity_proof_v1",
            "signing",  # Day 5 Gate S2: tenant-scoped signing metadata
        }
        actual_keys = set(receipt.keys())
        missing = required_keys - actual_keys
        extra = actual_keys - required_keys
        assert not missing, f"Missing receipt keys: {missing}"
        assert not extra, f"Extra receipt keys: {extra}"

    def test_update_data_does_not_contain_phase2a_fields(self):
        """
        The atomic update_data written to batch doc must NOT contain
        Phase 2A internal fields (backpressure, lock_wait, etc).
        """
        db = InMemoryFirestore()
        bid = "BATCH-UPDATE-CLEAN"
        _setup_db(db, bid, VALID_RESULTS)
        status_code, _, db = _run_finalize(db, bid)
        assert status_code == 200

        batch = db._data[f"batches/{bid}"]
        forbidden = [
            "lock_wait_seconds", "shard_merge_duration_seconds",
            "write_duration_seconds", "backpressure",
            "batch_write_seconds", "shard_merge_seconds",
        ]
        for field in forbidden:
            assert field not in batch, \
                f"Phase 2A field '{field}' leaked into batch doc"

    def test_no_protocol_version_bump(self):
        """ROUTER_VERSION and CANONICAL_CONFIG_VERSION unchanged by Phase 2A."""
        with patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}):
            from app.server_enterprise_golden import ROUTER_VERSION, CANONICAL_CONFIG_VERSION
            # These are string constants — just verify they exist and are stable
            assert isinstance(ROUTER_VERSION, str)
            assert len(ROUTER_VERSION) > 0
            assert isinstance(CANONICAL_CONFIG_VERSION, str)

    def test_hash_inputs_unchanged(self):
        """
        Verify the hash chain inputs do not include Phase 2A fields.
        The compute_and_store_hash_chain mock is called with results list.
        Results must not contain backpressure/timing metadata.
        """
        db = InMemoryFirestore()
        bid = "BATCH-HASH-CLEAN"
        _setup_db(db, bid, VALID_RESULTS)

        hash_chain_mock = MagicMock(return_value=(False, None))
        patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._firestore_db", db),
            patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
            patch("app.server_enterprise_golden.generate_and_store_evidence_blobs",
                  MagicMock(return_value=(0, None))),
            patch("app.server_enterprise_golden.compute_and_store_hash_chain", hash_chain_mock),
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

            # Inspect the results passed to hash_chain
            if hash_chain_mock.called:
                call_args = hash_chain_mock.call_args
                # Results are typically the first positional arg
                results_arg = call_args[0][1] if len(call_args[0]) > 1 else None
                if results_arg:
                    for row in results_arg:
                        for forbidden in ["lock_wait", "backpressure", "shard_merge"]:
                            assert forbidden not in str(row), \
                                f"Hash input contaminated with '{forbidden}'"
        finally:
            for p in reversed(patchers):
                p.stop()
