"""Day 4: Finalization Contract — Finalize Lock + Index Integrity Proof.

Tests:
- verify_index_integrity pure function (5 tests)
- acquire_finalize_lock / complete_finalize_state unit tests (7 tests)
- Endpoint tests: lock semantics through real endpoint (3 tests)
- Endpoint tests: index integrity enforcement with sign/anchor mocks (3 tests)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# In-memory Firestore mock
# ─────────────────────────────────────────────────────────────────────────────

class MockFirestoreDoc:
    def __init__(self, data=None, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class InMemoryFirestore:
    def __init__(self):
        self._data = {}

    def collection(self, name):
        return _CollectionRef(self, name)

    def transaction(self, **kwargs):
        return _InMemoryTransaction(self)


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._db, f"{self._path}/{doc_id}")

    def order_by(self, field):
        return _Query(self._db, self._path, order_field=field)

    def stream(self, transaction=None):
        prefix = self._path + "/"
        results = []
        for path, data in sorted(self._db._data.items()):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                if "/" not in remainder:
                    results.append(MockFirestoreDoc(data, exists=True))
        return results


class _Query:
    def __init__(self, db, collection_path, order_field=None):
        self._db = db
        self._collection_path = collection_path
        self._order_field = order_field

    def stream(self, transaction=None):
        prefix = self._collection_path + "/"
        results = []
        for path, data in sorted(self._db._data.items()):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                if "/" not in remainder:
                    results.append(MockFirestoreDoc(data, exists=True))
        if self._order_field:
            results.sort(key=lambda d: d.to_dict().get(self._order_field, 0))
        return results


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def collection(self, name):
        return _CollectionRef(self._db, f"{self._path}/{name}")

    def get(self, transaction=None):
        data = self._db._data.get(self._path)
        if data is not None:
            return MockFirestoreDoc(data, exists=True)
        return MockFirestoreDoc(exists=False)

    def set(self, data):
        self._db._data[self._path] = data.copy()

    def update(self, data):
        if self._path not in self._db._data:
            self._db._data[self._path] = {}
        # Support nested field paths (e.g. "veracity_receipt.index_integrity_proof_v1")
        for key, value in data.items():
            parts = key.split(".")
            if len(parts) > 1:
                target = self._db._data[self._path]
                for part in parts[:-1]:
                    if part not in target or not isinstance(target[part], dict):
                        target[part] = {}
                    target = target[part]
                target[parts[-1]] = value
            else:
                self._db._data[self._path][key] = value


class _InMemoryTransaction:
    """Transaction that reads/writes directly against InMemoryFirestore."""

    def __init__(self, db):
        self._db = db

    def get(self, ref):
        return ref.get()

    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data):
        ref.set(data)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

VALID_RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_EXACT",
     "confidence": 1.0, "global_index": 0},
    {"original": "Appple Inc", "resolved": "Apple Inc.", "layer": "L2_VECTOR",
     "confidence": 0.88, "global_index": 1},
    {"original": "xyzzy corp", "resolved": None, "layer": "L4_HUMAN",
     "confidence": 0.0, "global_index": 2},
]

MISSING_INDEX_RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_EXACT",
     "confidence": 1.0},
    {"original": "Appple Inc", "resolved": "Apple Inc.", "layer": "L2_VECTOR",
     "confidence": 0.88, "global_index": 1},
]

DUPLICATE_INDEX_RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_EXACT",
     "confidence": 1.0, "global_index": 0},
    {"original": "Appple Inc", "resolved": "Apple Inc.", "layer": "L2_VECTOR",
     "confidence": 0.88, "global_index": 0},
    {"original": "xyzzy corp", "resolved": None, "layer": "L4_HUMAN",
     "confidence": 0.0, "global_index": 2},
]


def _setup_db(db, batch_id, results, status="finalizing",
              finalize_state="none", finalize_lock=None):
    """Populate InMemoryFirestore with batch + shard + chunk docs.

    Sets batch_data["total"] = len(results) — the canonical field
    read by the handler via batch_data.get("total", ...).
    """
    created = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    batch_doc = {
        "trace_id": batch_id,
        "status": status,
        "dataset_type": "COMPANY",
        "timestamp": created,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": "tenant-test",
        "total": len(results),
        "total_records": len(results),
        "sharded": True,
        "shard_count": 1,
        "total_l3_spent_usd": 0.01,
        "finalize_state": finalize_state,
        "counts": {
            "total": len(results),
            "l0": 0, "l1": 0, "l2": 0, "l3": 0, "l4": 0,
            "l3_calls": 2, "l3_spent_usd": 0.01,
        },
    }
    if finalize_lock is not None:
        batch_doc["finalize_lock"] = finalize_lock
    db._data[f"batches/{batch_id}"] = batch_doc

    # Phase 2A: Create dedicated finalize state doc
    finalize_state_doc = {
        "finalize_state": finalize_state,
        "finalize_lock": finalize_lock,
        "batch_trace_id": batch_id,
    }
    db._data[f"batch_finalize_state/{batch_id}"] = finalize_state_doc

    db._data[f"batches/{batch_id}/shards/shard_0000"] = {
        "shard_id": 0,
        "start_index": 0,
        "end_index": len(results),
        "record_count": len(results),
        "status": "completed",
        "results_chunks": ["shard_0000_chunk_000000"],
        "counts": {"total": len(results), "l3_calls": 2, "l3_spent_usd": 0.01},
        "l3_spent_usd": 0.01,
        "duration_ms": 3000.0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    db._data[f"batches/{batch_id}/results_chunks/shard_0000_chunk_000000"] = {
        "start_index": 0,
        "count": len(results),
        "rows": results,
    }


def _bypass_transactional(func):
    """Replace @_finalize_transactional: call func directly, skip GCP."""
    def wrapper(transaction, *args, **kwargs):
        return func(transaction, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure function tests: verify_index_integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyIndexIntegrity:

    def setup_method(self):
        self._p1 = patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"})
        self._p2 = patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional)
        self._p1.start()
        self._p2.start()
        from app.server_enterprise_golden import verify_index_integrity
        self._verify = verify_index_integrity

    def teardown_method(self):
        self._p2.stop()
        self._p1.stop()

    def test_valid_indices(self):
        proof = self._verify(VALID_RESULTS, len(VALID_RESULTS))
        assert proof["verified"] is True
        assert proof["expected"] == len(VALID_RESULTS)
        assert proof["observed"] == len(VALID_RESULTS)
        assert proof["min_index"] == 0
        assert proof["max_index"] == len(VALID_RESULTS) - 1

    def test_missing_global_index(self):
        proof = self._verify(MISSING_INDEX_RESULTS, len(MISSING_INDEX_RESULTS))
        assert proof["verified"] is False
        assert proof["reason"] == "MISSING_GLOBAL_INDEX"
        assert proof["missing_global_index_rows"] == 1

    def test_duplicate_indices(self):
        proof = self._verify(DUPLICATE_INDEX_RESULTS, len(DUPLICATE_INDEX_RESULTS))
        assert proof["verified"] is False
        assert proof["reason"] == "INDEX_INTEGRITY_VIOLATION"
        assert proof["duplicate_count"] > 0

    def test_count_mismatch(self):
        proof = self._verify(VALID_RESULTS, 5)
        assert proof["verified"] is False
        assert proof["expected"] == 5
        assert proof["observed"] == 3

    def test_empty_results(self):
        proof = self._verify([], 0)
        assert proof["expected"] == 0
        assert proof["observed"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Lock unit tests against InMemoryFirestore
# ─────────────────────────────────────────────────────────────────────────────

class TestAcquireFinalizeLock:

    def setup_method(self):
        self._p = patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional)
        self._p.start()
        from app.server_enterprise_golden import acquire_finalize_lock, complete_finalize_state
        self._acquire = acquire_finalize_lock
        self._complete = complete_finalize_state

    def teardown_method(self):
        self._p.stop()

    def test_acquire_fresh_batch(self):
        """Phase 2A: Lock written to batch_finalize_state/{id}, not batches/{id}."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-FRESH"
        db._data[f"batch_finalize_state/{bid}"] = {"finalize_state": "none", "finalize_lock": None}
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "acquired"
        assert lock_id is not None
        state_doc = db._data[f"batch_finalize_state/{bid}"]
        assert state_doc["finalize_state"] == "finalizing"
        assert state_doc["finalize_lock"]["lock_id"] == lock_id

    def test_acquire_already_terminal_completed(self):
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-DONE"
        db._data[f"batch_finalize_state/{bid}"] = {"finalize_state": "completed", "finalize_lock": None}
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "already_terminal"
        assert lock_id is None

    def test_acquire_already_terminal_failed(self):
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-FAIL"
        db._data[f"batch_finalize_state/{bid}"] = {"finalize_state": "failed", "finalize_lock": None}
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "already_terminal"
        assert lock_id is None

    def test_acquire_active_lock_returns_locked(self):
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-ACTIVE"
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "finalizing",
            "finalize_lock": {"lock_id": "existing-lock", "expires_at": future},
        }
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "locked"
        assert lock_id is None
        assert db._data[f"batch_finalize_state/{bid}"]["finalize_lock"]["lock_id"] == "existing-lock"

    def test_acquire_expired_lock_succeeds(self):
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-EXPIRED"
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "finalizing",
            "finalize_lock": {"lock_id": "old-lock", "expires_at": past},
        }
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "acquired"
        assert lock_id is not None
        assert lock_id != "old-lock"

    def test_complete_state_ok(self):
        """Phase 2A: Terminal state written to batch_finalize_state/{id}."""
        db = InMemoryFirestore()
        bid = "BATCH-COMPLETE-OK"
        lock_id = "my-lock-123"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "finalizing",
            "finalize_lock": {"lock_id": lock_id},
        }
        result, mismatch = self._complete(bid, lock_id, "completed", db)
        assert result == "ok"
        assert mismatch is None
        assert db._data[f"batch_finalize_state/{bid}"]["finalize_state"] == "completed"
        assert db._data[f"batch_finalize_state/{bid}"]["finalize_lock"] is None

    def test_complete_state_lock_mismatch(self):
        db = InMemoryFirestore()
        bid = "BATCH-COMPLETE-MISMATCH"
        db._data[f"batch_finalize_state/{bid}"] = {
            "finalize_state": "finalizing",
            "finalize_lock": {"lock_id": "other-lock"},
        }
        result, mismatch = self._complete(bid, "wrong-lock", "completed", db)
        assert result == "lock_mismatch"
        assert mismatch == "other-lock"
        assert db._data[f"batch_finalize_state/{bid}"]["finalize_state"] == "finalizing"

    def test_backward_compat_no_finalize_state_doc(self):
        """Phase 2A: Lock acquired even if batch_finalize_state doc doesn't exist (pre-migration)."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-PREMIGRATION"
        # No batch_finalize_state doc exists
        result, lock_id = self._acquire(bid, "test", db)
        assert result == "acquired"
        assert lock_id is not None
        state_doc = db._data[f"batch_finalize_state/{bid}"]
        assert state_doc["finalize_state"] == "finalizing"
        assert state_doc["finalize_lock"]["lock_id"] == lock_id

    def test_5_parallel_finalize_only_1_acquires(self):
        """Phase 2A: 5 sequential lock attempts → 1 acquired + 4 locked, batch doc untouched."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-PARALLEL"
        db._data[f"batch_finalize_state/{bid}"] = {"finalize_state": "none", "finalize_lock": None}
        db._data[f"batches/{bid}"] = {"status": "finalizing", "finalize_state": "none"}
        batch_before = db._data[f"batches/{bid}"].copy()

        results = []
        for i in range(5):
            r, lid = self._acquire(bid, f"worker-{i}", db)
            results.append((r, lid))

        acquired = [r for r in results if r[0] == "acquired"]
        locked = [r for r in results if r[0] == "locked"]
        assert len(acquired) == 1
        assert len(locked) == 4
        # Batch doc untouched
        assert db._data[f"batches/{bid}"] == batch_before

    def test_batch_doc_untouched_during_lock(self):
        """Phase 2A: Batch doc fields unchanged after lock acquire/release cycle."""
        db = InMemoryFirestore()
        bid = "BATCH-LOCK-UNTOUCHED"
        db._data[f"batch_finalize_state/{bid}"] = {"finalize_state": "none", "finalize_lock": None}
        db._data[f"batches/{bid}"] = {
            "status": "finalizing", "total": 100, "tenant_id": "t1",
            "finalize_state": "none",
        }
        batch_before = db._data[f"batches/{bid}"].copy()

        result, lock_id = self._acquire(bid, "test", db)
        assert result == "acquired"
        # Batch doc unchanged
        assert db._data[f"batches/{bid}"] == batch_before

        self._complete(bid, lock_id, "completed", db)
        # Batch doc still unchanged
        assert db._data[f"batches/{bid}"] == batch_before


# ─────────────────────────────────────────────────────────────────────────────
# 3. Endpoint tests: lock semantics (REAL lock logic through endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalizeLockEndpoint:

    def _start_patches(self, db):
        """Start patches, return TestClient. Caller must call _stop_patches."""
        self._evidence_mock = MagicMock(return_value=(0, None))
        self._hash_chain_mock = MagicMock(return_value=(False, None))
        self._patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._firestore_db", db),
            patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
            patch("app.server_enterprise_golden.generate_and_store_evidence_blobs", self._evidence_mock),
            patch("app.server_enterprise_golden.compute_and_store_hash_chain", self._hash_chain_mock),
        ]
        for p in self._patchers:
            p.start()
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def _stop_patches(self):
        for p in reversed(self._patchers):
            p.stop()

    def test_active_lock_returns_409(self):
        db = InMemoryFirestore()
        bid = "BATCH-EP-LOCK-409"
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        _setup_db(db, bid, VALID_RESULTS, finalize_state="finalizing",
                  finalize_lock={"lock_id": "holder-lock",
                                 "locked_by": "other-worker",
                                 "locked_at": datetime.now(timezone.utc).isoformat(),
                                 "expires_at": future})
        try:
            client = self._start_patches(db)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 409
            # Phase 2A: Lock state in dedicated collection
            assert db._data[f"batch_finalize_state/{bid}"]["finalize_lock"]["lock_id"] == "holder-lock"
        finally:
            self._stop_patches()

    def test_expired_lock_acquires_and_completes(self):
        db = InMemoryFirestore()
        bid = "BATCH-EP-LOCK-EXP"
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        _setup_db(db, bid, VALID_RESULTS, finalize_state="finalizing",
                  finalize_lock={"lock_id": "stale-lock",
                                 "locked_by": "crashed-worker",
                                 "locked_at": past,
                                 "expires_at": past})
        try:
            client = self._start_patches(db)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 200
            batch = db._data[f"batches/{bid}"]
            assert batch["status"] == "completed"
            # Phase 2A: Lock and finalize_state now in dedicated collection
            state_doc = db._data[f"batch_finalize_state/{bid}"]
            assert state_doc.get("finalize_lock") is None
            assert state_doc["finalize_state"] == "completed"
        finally:
            self._stop_patches()

    def test_terminal_state_returns_already_terminal(self):
        db = InMemoryFirestore()
        bid = "BATCH-EP-TERMINAL"
        _setup_db(db, bid, VALID_RESULTS, status="finalizing",
                  finalize_state="completed")
        try:
            client = self._start_patches(db)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": bid, "tenant_id": "tenant-test",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "already_terminal"
        finally:
            self._stop_patches()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Endpoint tests: index integrity enforcement (sign/anchor mocks)
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalizeIndexIntegrityEndpoint:

    def _run_finalize(self, db, batch_id):
        """Run finalize endpoint. Returns (status_code, resp_json, batch_doc,
        state_doc, evidence_mock, hash_chain_mock)."""
        evidence_mock = MagicMock(return_value=(0, None))
        hash_chain_mock = MagicMock(return_value=(False, None))
        patchers = [
            patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0"}),
            patch("app.server_enterprise_golden._firestore_db", db),
            patch("app.server_enterprise_golden.HAS_FORENSIC_SIGNING", True),
            patch("app.server_enterprise_golden._finalize_transactional", _bypass_transactional),
            patch("app.server_enterprise_golden.generate_and_store_evidence_blobs", evidence_mock),
            patch("app.server_enterprise_golden.compute_and_store_hash_chain", hash_chain_mock),
        ]
        for p in patchers:
            p.start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            resp = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": batch_id, "tenant_id": "tenant-test",
            })
            batch = db._data.get(f"batches/{batch_id}", {})
            state_doc = db._data.get(f"batch_finalize_state/{batch_id}", {})
            return resp.status_code, resp.json(), batch, state_doc, evidence_mock, hash_chain_mock
        finally:
            for p in reversed(patchers):
                p.stop()

    def test_count_mismatch_returns_422_no_sign(self):
        """batch.total=5 but only 2 results → count mismatch → 422."""
        db = InMemoryFirestore()
        bid = "BATCH-IDX-MISMATCH"
        # Use VALID_RESULTS (3 rows) but override batch.total to 5
        _setup_db(db, bid, VALID_RESULTS)
        db._data[f"batches/{bid}"]["total"] = 5
        db._data[f"batches/{bid}"]["total_records"] = 5
        status_code, resp_json, batch, state_doc, evidence_mock, hash_chain_mock = self._run_finalize(db, bid)

        assert status_code == 422
        assert batch["status"] == "failed"
        # Phase 2A: finalize_state and lock now in dedicated collection
        assert state_doc["finalize_state"] == "failed"
        assert state_doc.get("finalize_lock") is None
        proof = batch.get("veracity_receipt", {}).get("index_integrity_proof_v1", {})
        assert proof["verified"] is False
        assert proof["reason"] == "INDEX_INTEGRITY_VIOLATION"
        assert proof["expected"] == 5
        assert proof["observed"] == 3
        evidence_mock.assert_not_called()
        hash_chain_mock.assert_not_called()

    def test_global_index_auto_assigned_by_fetch(self):
        """Rows without global_index get it assigned by fetch_sharded_results_deterministic."""
        db = InMemoryFirestore()
        bid = "BATCH-IDX-AUTO"
        _setup_db(db, bid, MISSING_INDEX_RESULTS)
        status_code, resp_json, batch, state_doc, evidence_mock, hash_chain_mock = self._run_finalize(db, bid)

        # Should PASS now — global_index auto-assigned during fetch
        assert status_code == 200
        assert batch["status"] == "completed"
        proof = batch.get("veracity_receipt", {}).get("index_integrity_proof_v1", {})
        assert proof["verified"] is True
        assert proof["expected"] == len(MISSING_INDEX_RESULTS)
        assert proof["observed"] == len(MISSING_INDEX_RESULTS)

    def test_valid_indices_completes_with_proof(self):
        db = InMemoryFirestore()
        bid = "BATCH-IDX-VALID"
        _setup_db(db, bid, VALID_RESULTS)
        status_code, resp_json, batch, state_doc, evidence_mock, hash_chain_mock = self._run_finalize(db, bid)

        assert status_code == 200
        assert batch["status"] == "completed"
        assert state_doc["finalize_state"] == "completed"
        assert state_doc.get("finalize_lock") is None
        proof = batch.get("veracity_receipt", {}).get("index_integrity_proof_v1", {})
        assert proof["verified"] is True
        assert proof["expected"] == len(VALID_RESULTS)
        assert proof["observed"] == len(VALID_RESULTS)
        evidence_mock.assert_called_once()
