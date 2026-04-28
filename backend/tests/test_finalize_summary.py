"""Regression tests for sharded batch dashboard parity.

Verifies that /internal/finalize-batch writes all dashboard-expected fields:
duration_seconds, auto_resolved_pct, flagged_count, counts (long keys),
mode, cost, stats, llm_budget_summary.

These fields were previously missing, causing 0.0s duration, 0% auto-resolved,
and "Legacy Batch" display on the enterprise dashboard.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# In-memory Firestore mock (same pattern as test_shard_finalize.py)
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


class _InMemoryTransaction:
    def __init__(self, db):
        self._db = db

    def get(self, ref):
        return ref.get()

    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data):
        ref.set(data)


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


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────

BATCH_ID = "BATCH-FINALIZE-TEST-001"

# 10 results: mix of layers for MIXED mode
MIXED_RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_ORG", "confidence": 0.95, "global_index": 0},
    {"original": "Microsoft", "resolved": "Microsoft Corporation", "layer": "L1_ORG", "confidence": 0.90, "global_index": 1},
    {"original": "John Smith", "resolved": "JOHN SMITH", "layer": "L1_PERSON", "confidence": 0.85, "global_index": 2},
    {"original": "Jane Doe", "resolved": "JANE DOE", "layer": "L1_PERSON", "confidence": 0.80, "global_index": 3},
    {"original": "Appple Inc", "resolved": "Apple Inc.", "layer": "L2_VECTOR", "confidence": 0.88, "global_index": 4},
    {"original": "test division", "resolved": "Tesla, Inc.", "layer": "L3_LLM", "confidence": 0.75, "global_index": 5},
    {"original": "xyzzy corp", "resolved": None, "layer": "L4_HUMAN", "confidence": 0.0, "global_index": 6},
    {"original": "", "resolved": None, "layer": "L0_GARBAGE_BLANK", "confidence": 0.0, "global_index": 7},
    {"original": "12345", "resolved": None, "layer": "L0_GARBAGE_NUMERIC", "confidence": 0.0, "global_index": 8},
    {"original": "Googl Inc", "resolved": "Alphabet Inc.", "layer": "L2_VECTOR", "confidence": 0.82, "global_index": 9},
]

# 6 results: company mode
COMPANY_RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_EXACT", "confidence": 1.0, "global_index": 0},
    {"original": "apple", "resolved": "Apple Inc.", "layer": "L1_NORM", "confidence": 0.95, "global_index": 1},
    {"original": "Appple Inc", "resolved": "Apple Inc.", "layer": "L2_VECTOR", "confidence": 0.88, "global_index": 2},
    {"original": "test division", "resolved": "Tesla, Inc.", "layer": "L3_LLM", "confidence": 0.75, "global_index": 3},
    {"original": "xyzzy corp", "resolved": None, "layer": "L4_HUMAN", "confidence": 0.0, "global_index": 4},
    {"original": "", "resolved": None, "layer": "L0_GARBAGE_BLANK", "confidence": 0.0, "global_index": 5},
]


def _setup_finalize_db(db, batch_id, dataset_type, results, l3_calls=5, l3_spent=0.025):
    """Populate InMemoryFirestore with batch + shard docs + result chunks."""
    created = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    # Batch doc (as written by try_complete_batch at "finalizing" stage)
    db._data[f"batches/{batch_id}"] = {
        "trace_id": batch_id,
        "status": "finalizing",
        "dataset_type": dataset_type,
        "timestamp": created,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": "tenant-test",
        "total": len(results),
        "total_records": len(results),
        "sharded": True,
        "shard_count": 1,
        "total_l3_spent_usd": l3_spent,
        "counts": {
            "total": len(results),
            "l0": sum(1 for r in results if r.get("layer", "").startswith("L0_")),
            "l1": sum(1 for r in results if r.get("layer", "").startswith("L1_")),
            "l2": sum(1 for r in results if r.get("layer", "").startswith("L2_") or r.get("layer") == "L2_VECTOR"),
            "l3": sum(1 for r in results if r.get("layer", "").startswith("L3_")),
            "l4": sum(1 for r in results if r.get("layer") == "L4_HUMAN"),
            "l3_calls": l3_calls,
            "l3_spent_usd": l3_spent,
        },
    }

    # Single shard doc
    db._data[f"batches/{batch_id}/shards/shard_0000"] = {
        "shard_id": 0,
        "start_index": 0,
        "end_index": len(results),
        "record_count": len(results),
        "status": "completed",
        "results_chunks": ["shard_0000_chunk_000000"],
        "counts": {
            "total": len(results),
            "l3_calls": l3_calls,
            "l3_spent_usd": l3_spent,
        },
        "l3_spent_usd": l3_spent,
        "duration_ms": 3000.0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    # Result chunk (what fetch_sharded_results_deterministic loads)
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


def _run_finalize(db, batch_id):
    """Call the finalize endpoint and return the batch doc after update."""
    # Patch all dependencies
    patches = {
        "app.server_enterprise_golden._firestore_db": db,
        "app.server_enterprise_golden.HAS_FORENSIC_SIGNING": False,
        "app.server_enterprise_golden._finalize_transactional": _bypass_transactional,
    }

    with patch.dict(os.environ, {"L3_MAX_COST_USD": "10.0", "HMAC_SCOPE_KEY": "aa" * 32}):
        for target, value in patches.items():
            patch(target, value).start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": batch_id,
                "tenant_id": "tenant-test",
            })
            assert response.status_code == 200, f"Finalize failed: {response.text}"
        finally:
            patch.stopall()

    return db._data.get(f"batches/{batch_id}", {})


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalizeDashboardParity:
    """Verify finalize writes all dashboard-expected fields."""

    def test_finalize_writes_duration_seconds(self):
        """duration_seconds must be > 0 (batch created 5 min ago)."""
        db = InMemoryFirestore()
        _setup_finalize_db(db, BATCH_ID, "MIXED", MIXED_RESULTS)
        batch = _run_finalize(db, BATCH_ID)

        assert batch["status"] == "completed"
        assert batch["duration_seconds"] > 0
        assert batch["duration_ms"] > 0
        # Created 5 min ago → duration should be ~300s (allow wide tolerance)
        assert 100 < batch["duration_seconds"] < 600

    def test_finalize_writes_auto_resolved_mixed(self):
        """MIXED mode: auto_resolved = records with confidence >= 0.70 (excluding L0)."""
        db = InMemoryFirestore()
        _setup_finalize_db(db, BATCH_ID, "MIXED", MIXED_RESULTS)
        batch = _run_finalize(db, BATCH_ID)

        # From MIXED_RESULTS: 8 non-garbage records, 6 have confidence >= 0.70
        # (Apple 0.95, Microsoft 0.90, John 0.85, Jane 0.80, Appple 0.88, test_division 0.75)
        # Googl 0.82 also >= 0.70, xyzzy 0.0 is not
        # So auto_resolved = 7 (all non-garbage with conf >= 0.70)
        assert batch["auto_resolved"] == 7
        assert batch["auto_resolved_pct"] > 0
        assert batch["flagged_count"] == 8 - 7  # valid - auto_resolved = 1

    def test_finalize_writes_auto_resolved_company(self):
        """COMPANY mode: auto_resolved = l1 + l2 + l3 (layer-based)."""
        db = InMemoryFirestore()
        bid = "BATCH-COMPANY-001"
        _setup_finalize_db(db, bid, "COMPANY", COMPANY_RESULTS)
        batch = _run_finalize(db, bid)

        # l1_exact=1, l1_norm=1, l2=1, l3=1 → auto_resolved = 4
        assert batch["auto_resolved"] == 4
        # l4 = 1 → flagged_count = 1 (company mode uses l4)
        assert batch["flagged_count"] == 1

    def test_finalize_writes_dashboard_counts(self):
        """counts dict must have both short keys (l0,l1,...) and long keys (l0_quarantined, l1_resolved,...)."""
        db = InMemoryFirestore()
        bid = "BATCH-COUNTS-001"
        _setup_finalize_db(db, bid, "COMPANY", COMPANY_RESULTS)
        batch = _run_finalize(db, bid)

        counts = batch["counts"]
        # Long keys (dashboard reads these)
        assert "l0_quarantined" in counts
        assert "l1_resolved" in counts
        assert "l2_resolved" in counts
        assert "l3_resolved" in counts
        assert "l4_flagged" in counts
        # Short keys (backward compat)
        assert "l0" in counts
        assert "l1" in counts
        # Verify values
        assert counts["l0_quarantined"] == 1  # 1 blank
        assert counts["l1_resolved"] == 2  # 1 exact + 1 norm
        assert counts["l2_resolved"] == 1
        assert counts["l3_resolved"] == 1
        assert counts["l4_flagged"] == 1

    def test_finalize_writes_llm_budget_summary(self):
        """llm_budget_summary must contain spent_usd matching aggregated shard data."""
        db = InMemoryFirestore()
        bid = "BATCH-BUDGET-001"
        _setup_finalize_db(db, bid, "MIXED", MIXED_RESULTS, l3_calls=5, l3_spent=0.025)
        batch = _run_finalize(db, bid)

        lbs = batch["llm_budget_summary"]
        assert lbs["spent_usd"] == 0.025
        assert lbs["calls"] == 5
        assert lbs["budget_usd"] == 10.0
        # cost field for frontend fallback
        assert batch["cost"] == 0.025

    def test_finalize_writes_mode(self):
        """mode and dataset_type match the batch doc."""
        db = InMemoryFirestore()
        bid = "BATCH-MODE-001"
        _setup_finalize_db(db, bid, "MIXED", MIXED_RESULTS)
        batch = _run_finalize(db, bid)

        assert batch["mode"] == "mixed"
        assert batch["dataset_type"] == "MIXED"
