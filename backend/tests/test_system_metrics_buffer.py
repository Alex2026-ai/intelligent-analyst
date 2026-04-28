"""
test_system_metrics_buffer.py — Day 6: Unit tests for bounded-buffer metrics.

Reuses InMemoryFirestore from test_budget_ledger.py pattern.
"""

import pytest
from app.metrics.system_metrics import (
    compute_p95,
    record_finalize_latency,
    record_shard_latency,
    record_l3_cache_stats,
    record_failover_stats,
    record_ledger_snapshot,
    get_system_vitals,
)


# ── InMemoryFirestore (same pattern as test_budget_ledger.py) ────────────────

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


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._db, f"{self._path}/{doc_id}")


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

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


# ── Tests ────────────────────────────────────────────────────────────────────


class TestFirstSampleCreatesDoc:
    def test_first_sample_creates_doc(self):
        db = InMemoryFirestore()
        result = record_finalize_latency(db, 150.0)
        assert result is True
        doc = db._data.get("system_metrics/finalize")
        assert doc is not None
        assert len(doc["samples"]) == 1
        assert doc["samples"][0] == 150.0
        assert doc["sample_count"] == 1


class TestBufferTrimsTo100:
    def test_buffer_trims_to_100(self):
        db = InMemoryFirestore()
        # Pre-populate with 100 samples
        db._data["system_metrics/finalize"] = {
            "samples": list(range(100)),
            "sample_count": 100,
        }
        # Add one more
        result = record_finalize_latency(db, 999.0)
        assert result is True
        doc = db._data["system_metrics/finalize"]
        assert len(doc["samples"]) == 100
        # Oldest (0) should be evicted, newest (999.0) present
        assert doc["samples"][-1] == 999.0
        assert 0 not in doc["samples"]


class TestSampleCountTotal:
    def test_sample_count_total(self):
        db = InMemoryFirestore()
        # Pre-populate with 100 samples, all-time count=200
        db._data["system_metrics/finalize"] = {
            "samples": list(range(100)),
            "sample_count": 200,
        }
        record_finalize_latency(db, 50.0)
        doc = db._data["system_metrics/finalize"]
        # sample_count = all-time, not buffer len
        assert doc["sample_count"] == 201
        assert len(doc["samples"]) == 100


class TestP95KnownDistribution:
    def test_p95_known_distribution(self):
        samples = list(range(1, 101))  # [1, 2, ..., 100]
        assert compute_p95(samples) == 95.0


class TestP95Empty:
    def test_p95_empty(self):
        assert compute_p95([]) == 0.0


class TestShardSeparateDoc:
    def test_shard_separate_doc(self):
        db = InMemoryFirestore()
        record_shard_latency(db, 200.0)
        assert "system_metrics/shards" in db._data
        assert "system_metrics/finalize" not in db._data


class TestL3CacheIncrements:
    def test_l3_cache_increments(self):
        db = InMemoryFirestore()
        record_l3_cache_stats(db, l3_total_calls=10, l3_cache_hits=3, l3_unknown_cached=1)
        record_l3_cache_stats(db, l3_total_calls=5, l3_cache_hits=2, l3_unknown_cached=0)
        doc = db._data["system_metrics/l3_cache"]
        assert doc["l3_total_calls"] == 15
        assert doc["l3_cache_hits"] == 5
        assert doc["l3_unknown_cached"] == 1


class TestNoDbReturnsFalse:
    def test_no_db_returns_false(self):
        assert record_finalize_latency(None, 100.0) is False
        assert record_shard_latency(None, 100.0) is False
        assert record_l3_cache_stats(None, 10, 3, 1) is False
        assert record_failover_stats(None, 1, 10) is False
        assert record_ledger_snapshot(None, "t1", 10.0, 5.0, 0.0, True) is False


class TestGetSystemVitalsEmpty:
    def test_get_system_vitals_empty(self):
        db = InMemoryFirestore()
        vitals = get_system_vitals(db)
        assert vitals["finalize_p95_ms"] == 0.0
        assert vitals["shard_p95_ms"] == 0.0
        assert vitals["l3_cache_hit_rate"] == 0.0
        assert vitals["failover_rate_percent"] == 0.0
        assert vitals["ledger_integrity"] == "PASS"
        assert vitals["finalize_sample_count"] == 0
        assert vitals["shard_sample_count"] == 0
        assert "collected_at" in vitals


class TestGetSystemVitalsWithData:
    def test_get_system_vitals_with_data(self):
        db = InMemoryFirestore()

        # Finalize samples: [10, 20, 30, ..., 100] → p95 = 100.0
        db._data["system_metrics/finalize"] = {
            "samples": list(range(10, 110, 10)),
            "sample_count": 10,
        }
        # Shard samples
        db._data["system_metrics/shards"] = {
            "samples": [50.0, 100.0, 150.0, 200.0],
            "sample_count": 4,
        }
        # L3 cache: 100 total, 30 hits, 5 unknown
        db._data["system_metrics/l3_cache"] = {
            "l3_total_calls": 100,
            "l3_cache_hits": 30,
            "l3_unknown_cached": 5,
        }
        # Failover: 2 out of 50
        db._data["system_metrics/failover"] = {
            "failover_count": 2,
            "total_l3_calls": 50,
            "outcomes": [1, 1],
        }
        # Ledger: healthy
        db._data["system_metrics/ledger"] = {
            "credits_reserved_usd": 10.0,
            "credits_spent_usd": 5.0,
        }

        vitals = get_system_vitals(db)
        assert vitals["finalize_p95_ms"] == 100.0
        assert vitals["shard_p95_ms"] == 200.0
        assert vitals["l3_cache_hit_rate"] == 30.0
        assert vitals["l3_unknown_cache_rate"] == 5.0
        assert vitals["failover_rate_percent"] == 4.0
        assert vitals["ledger_integrity"] == "PASS"
        assert vitals["finalize_sample_count"] == 10
        assert vitals["shard_sample_count"] == 4
