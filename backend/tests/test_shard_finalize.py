"""
test_shard_finalize.py — Unit tests for Day 3 shard grid hardening.

Tests:
- Enriched shard receipt schema (results_chunks, duration_ms)
- build_shard_receipts() pure function
- try_complete_batch() status semantics ("finalizing" not "completed")
- fetch_sharded_results_deterministic()
- _fail_batch()
- /internal/finalize-batch idempotency and fail-closed behavior

All Firestore interactions are mocked — no real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from app.sharding import (
    update_shard_status,
    build_shard_receipts,
    try_complete_batch,
    _shard_doc_id,
)


# =============================================================================
# In-memory Firestore mock (same pattern as test_budget_ledger.py)
# =============================================================================

class MockFirestoreDoc:
    def __init__(self, data=None, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class InMemoryFirestore:
    def __init__(self):
        self._data = {}  # path -> dict

    def collection(self, name):
        return _CollectionRef(self, name)

    def transaction(self, **kwargs):
        return MockTransaction()


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._db, f"{self._path}/{doc_id}")

    def order_by(self, field):
        return _Query(self._db, self._path, order_field=field)

    def stream(self, transaction=None):
        """Yield all docs whose path starts with this collection path."""
        prefix = self._path + "/"
        results = []
        for path, data in sorted(self._db._data.items()):
            if path.startswith(prefix):
                # Only direct children (no nested subcollections)
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
        self._db._data[self._path].update(data)


class MockTransaction:
    def __init__(self):
        self.updates = []
        self.sets = []

    def update(self, ref, data):
        ref.update(data)
        self.updates.append((ref, data))

    def set(self, ref, data):
        ref.set(data)
        self.sets.append((ref, data))


# =============================================================================
# build_shard_receipts tests
# =============================================================================

class TestBuildShardReceipts:
    def test_empty_input(self):
        assert build_shard_receipts([]) == []

    def test_single_shard(self):
        shard_statuses = [{
            "shard_id": 0,
            "start_index": 0,
            "end_index": 500,
            "record_count": 500,
            "results_chunks": ["shard_0000_chunk_000000"],
            "counts": {"total": 500, "l1": 400, "l2": 50, "l3": 10, "l4": 40},
            "l3_spent_usd": 0.05,
            "duration_ms": 1234.5,
            "finished_at": "2026-02-22T10:00:00",
        }]
        receipts = build_shard_receipts(shard_statuses)
        assert len(receipts) == 1
        assert receipts[0]["shard_id"] == 0
        assert receipts[0]["results_chunks"] == ["shard_0000_chunk_000000"]
        assert receipts[0]["duration_ms"] == 1234.5
        assert receipts[0]["l3_spent_usd"] == 0.05

    def test_multiple_shards_ordered(self):
        """Receipts are returned sorted by shard_id even if input is unordered."""
        shard_statuses = [
            {"shard_id": 2, "start_index": 2000, "end_index": 3000, "record_count": 1000,
             "results_chunks": ["shard_0002_chunk_000000", "shard_0002_chunk_000500"],
             "counts": {"total": 1000}, "l3_spent_usd": 0.0, "duration_ms": 500.0, "finished_at": "t3"},
            {"shard_id": 0, "start_index": 0, "end_index": 1000, "record_count": 1000,
             "results_chunks": ["shard_0000_chunk_000000", "shard_0000_chunk_000500"],
             "counts": {"total": 1000}, "l3_spent_usd": 0.1, "duration_ms": 800.0, "finished_at": "t1"},
            {"shard_id": 1, "start_index": 1000, "end_index": 2000, "record_count": 1000,
             "results_chunks": ["shard_0001_chunk_000000", "shard_0001_chunk_000500"],
             "counts": {"total": 1000}, "l3_spent_usd": 0.05, "duration_ms": 600.0, "finished_at": "t2"},
        ]
        receipts = build_shard_receipts(shard_statuses)
        assert [r["shard_id"] for r in receipts] == [0, 1, 2]

    def test_missing_fields_use_defaults(self):
        """Shard doc without results_chunks/duration_ms → defaults to empty/None."""
        shard_statuses = [{"shard_id": 0}]
        receipts = build_shard_receipts(shard_statuses)
        assert receipts[0]["results_chunks"] == []
        assert receipts[0]["duration_ms"] is None
        assert receipts[0]["counts"] == {}


# =============================================================================
# update_shard_status enrichment tests
# =============================================================================

class TestUpdateShardStatusEnriched:
    def _setup_shard(self, db, batch_id="BATCH-001", shard_id=0):
        path = f"batches/{batch_id}/shards/{_shard_doc_id(shard_id)}"
        db._data[path] = {
            "batch_id": batch_id,
            "shard_id": shard_id,
            "status": "running",
        }

    def test_results_chunks_persisted(self):
        db = InMemoryFirestore()
        self._setup_shard(db)
        chunks = ["shard_0000_chunk_000000", "shard_0000_chunk_000500"]

        # Mock the Increment import
        with patch("app.sharding.Increment", create=True):
            result = update_shard_status(
                "BATCH-001", 0, "completed", db,
                counts={"total": 1000},
                results_chunks=chunks,
                duration_ms=1500.3,
            )

        assert result is True
        path = "batches/BATCH-001/shards/shard_0000"
        assert db._data[path]["results_chunks"] == chunks

    def test_duration_ms_persisted(self):
        db = InMemoryFirestore()
        self._setup_shard(db)

        with patch("app.sharding.Increment", create=True):
            result = update_shard_status(
                "BATCH-001", 0, "completed", db,
                duration_ms=2345.678,
            )

        assert result is True
        path = "batches/BATCH-001/shards/shard_0000"
        assert db._data[path]["duration_ms"] == 2345.7  # Rounded to 1 decimal

    def test_no_enrichment_when_none(self):
        """When results_chunks and duration_ms are None, they aren't written."""
        db = InMemoryFirestore()
        self._setup_shard(db)

        with patch("app.sharding.Increment", create=True):
            update_shard_status("BATCH-001", 0, "completed", db)

        path = "batches/BATCH-001/shards/shard_0000"
        assert "results_chunks" not in db._data[path]
        assert "duration_ms" not in db._data[path]


# =============================================================================
# try_complete_batch status semantics tests
# =============================================================================

class TestTryCompleteBatchFinalizing:
    """Verify try_complete_batch sets 'finalizing' not 'completed'."""

    def _make_db_with_shards(self, batch_id, shard_data_list):
        """Helper: create DB with batch doc + shard docs."""
        db = InMemoryFirestore()
        db._data[f"batches/{batch_id}"] = {"status": "processing"}

        for s in shard_data_list:
            shard_id = s["shard_id"]
            path = f"batches/{batch_id}/shards/{_shard_doc_id(shard_id)}"
            db._data[path] = s
        return db

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_all_completed_returns_finalize_dict(self):
        """All shards completed → returns dict with action='finalize'."""
        db = self._make_db_with_shards("BATCH-001", [
            {"shard_id": 0, "status": "completed", "record_count": 500,
             "counts": {"total": 500, "l1": 400}, "l3_spent_usd": 0.01,
             "results_chunks": ["shard_0000_chunk_000000"], "duration_ms": 100},
            {"shard_id": 1, "status": "completed", "record_count": 500,
             "counts": {"total": 500, "l1": 450}, "l3_spent_usd": 0.02,
             "results_chunks": ["shard_0001_chunk_000000"], "duration_ms": 200},
        ])

        result = try_complete_batch("BATCH-001", "tenant-1", db)

        assert isinstance(result, dict)
        assert result["action"] == "finalize"
        assert len(result["shard_receipts"]) == 2
        assert result["total_l3_spent"] == pytest.approx(0.03)
        assert result["shards_completed"] == 2

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_sets_finalizing_status(self):
        """Batch status must be 'finalizing', not 'completed'."""
        db = self._make_db_with_shards("BATCH-002", [
            {"shard_id": 0, "status": "completed", "record_count": 100,
             "counts": {"total": 100}, "l3_spent_usd": 0.0,
             "results_chunks": ["shard_0000_chunk_000000"]},
        ])

        try_complete_batch("BATCH-002", "tenant-1", db)

        batch_data = db._data["batches/BATCH-002"]
        assert batch_data["status"] == "finalizing"
        assert batch_data.get("status") != "completed"

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_failed_shard_sets_failed(self):
        """At least one shard failed → batch status = 'failed', returns True."""
        db = self._make_db_with_shards("BATCH-003", [
            {"shard_id": 0, "status": "completed", "record_count": 500,
             "counts": {"total": 500}, "l3_spent_usd": 0.0},
            {"shard_id": 1, "status": "failed", "record_count": 500,
             "last_error": "OOM", "l3_spent_usd": 0.0},
        ])

        result = try_complete_batch("BATCH-003", "tenant-1", db)

        assert result is True
        assert db._data["batches/BATCH-003"]["status"] == "failed"

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_still_running_returns_false(self):
        """Not all shards done → returns False."""
        db = self._make_db_with_shards("BATCH-004", [
            {"shard_id": 0, "status": "completed", "record_count": 500,
             "counts": {"total": 500}, "l3_spent_usd": 0.0},
            {"shard_id": 1, "status": "running", "record_count": 500,
             "counts": None, "l3_spent_usd": 0.0},
        ])

        result = try_complete_batch("BATCH-004", "tenant-1", db)
        assert result is False

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_shard_receipts_in_order(self):
        """Shard receipts in finalize dict are ordered by shard_id."""
        db = self._make_db_with_shards("BATCH-005", [
            {"shard_id": 2, "status": "completed", "record_count": 100,
             "counts": {"total": 100}, "l3_spent_usd": 0.0,
             "results_chunks": ["shard_0002_chunk_000000"], "duration_ms": 50},
            {"shard_id": 0, "status": "completed", "record_count": 100,
             "counts": {"total": 100}, "l3_spent_usd": 0.0,
             "results_chunks": ["shard_0000_chunk_000000"], "duration_ms": 60},
            {"shard_id": 1, "status": "completed", "record_count": 100,
             "counts": {"total": 100}, "l3_spent_usd": 0.0,
             "results_chunks": ["shard_0001_chunk_000000"], "duration_ms": 70},
        ])

        result = try_complete_batch("BATCH-005", "tenant-1", db)
        shard_ids = [r["shard_id"] for r in result["shard_receipts"]]
        assert shard_ids == [0, 1, 2]

    @patch("app.sharding._firestore_transactional", lambda func: func)
    def test_aggregated_counts(self):
        """Aggregated counts correctly sum across shards."""
        db = self._make_db_with_shards("BATCH-006", [
            {"shard_id": 0, "status": "completed", "record_count": 500,
             "counts": {"total": 500, "l1": 400, "l2": 50, "l3": 10, "l4": 40},
             "l3_spent_usd": 0.05, "results_chunks": ["c1"]},
            {"shard_id": 1, "status": "completed", "record_count": 500,
             "counts": {"total": 500, "l1": 300, "l2": 100, "l3": 20, "l4": 80},
             "l3_spent_usd": 0.10, "results_chunks": ["c2"]},
        ])

        result = try_complete_batch("BATCH-006", "tenant-1", db)
        assert result["agg_counts"]["l1"] == 700
        assert result["agg_counts"]["l2"] == 150
        assert result["agg_counts"]["l3"] == 30
        assert result["agg_counts"]["l4"] == 120
        assert result["total_l3_spent"] == pytest.approx(0.15)


# =============================================================================
# _fail_batch tests
# =============================================================================

class TestFailBatch:
    def test_fail_batch_sets_status(self):
        from app.server_enterprise_golden import _fail_batch

        db = InMemoryFirestore()
        db._data["batches/BATCH-001"] = {"status": "finalizing"}

        _fail_batch("BATCH-001", "TEST_REASON: something broke", db)

        assert db._data["batches/BATCH-001"]["status"] == "failed"
        assert "TEST_REASON" in db._data["batches/BATCH-001"]["error_reason"]

    def test_fail_batch_no_db(self):
        """No crash when db is None."""
        from app.server_enterprise_golden import _fail_batch
        _fail_batch("BATCH-001", "reason", None)  # Should not raise


# =============================================================================
# fetch_sharded_results_deterministic tests
# =============================================================================

class TestFetchShardedResultsDeterministic:
    @patch("app.server_enterprise_golden._firestore_db")
    def test_loads_in_shard_order(self, mock_db):
        from app.server_enterprise_golden import fetch_sharded_results_deterministic

        # Build mock Firestore with 2 shards, each with 1 chunk
        db = InMemoryFirestore()
        db._data["batches/B1/results_chunks/shard_0000_chunk_000000"] = {
            "rows": [{"original": "Apple", "layer": "L1_EXACT"}]
        }
        db._data["batches/B1/results_chunks/shard_0001_chunk_000000"] = {
            "rows": [{"original": "Google", "layer": "L2_VECTOR"}]
        }

        mock_db.__bool__ = lambda self: True

        # Patch _firestore_db at module level
        with patch("app.server_enterprise_golden._firestore_db", db):
            shard_receipts = [
                {"shard_id": 0, "results_chunks": ["shard_0000_chunk_000000"]},
                {"shard_id": 1, "results_chunks": ["shard_0001_chunk_000000"]},
            ]
            results = fetch_sharded_results_deterministic("B1", shard_receipts)

        assert len(results) == 2
        assert results[0]["original"] == "Apple"
        assert results[1]["original"] == "Google"

    @patch("app.server_enterprise_golden._firestore_db")
    def test_empty_results_chunks_fails_closed(self, mock_db):
        from app.server_enterprise_golden import fetch_sharded_results_deterministic

        db = InMemoryFirestore()
        with patch("app.server_enterprise_golden._firestore_db", db):
            shard_receipts = [
                {"shard_id": 0, "results_chunks": []},  # Empty → fail-closed
            ]
            results = fetch_sharded_results_deterministic("B1", shard_receipts)
        assert results == []

    @patch("app.server_enterprise_golden._firestore_db")
    def test_missing_chunk_fails_closed(self, mock_db):
        from app.server_enterprise_golden import fetch_sharded_results_deterministic

        db = InMemoryFirestore()
        # Chunk doc doesn't exist
        with patch("app.server_enterprise_golden._firestore_db", db):
            shard_receipts = [
                {"shard_id": 0, "results_chunks": ["shard_0000_chunk_000000"]},
            ]
            results = fetch_sharded_results_deterministic("B1", shard_receipts)
        assert results == []
