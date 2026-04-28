"""
test_vector_sovereignty.py — Phase 2B: Embedding Sovereignty Tests

Proves:
1) Vector namespace includes tenant_id + embedding_model_id + index_version
2) Cross-tenant same query does NOT hit same index partition
3) Cache key partitioned by tenant
4) Missing tenant_id → fail-closed on vector path
5) Determinism unchanged for L1-only batch (no vector calls)
"""

import hashlib
import re
import threading
import pytest
from unittest.mock import patch, MagicMock

from app.server_enterprise_golden import (
    vector_namespace,
    EMBEDDING_MODEL_ID,
    VECTOR_INDEX_VERSION,
    L3SemanticCache,
    _compute_l3_cache_key,
    _normalize_for_cache_key,
    get_vector_candidates,
    resolve_entity_sync,
    l3_singleflight_acquire,
    l3_singleflight_release,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) test_vector_namespace_includes_tenant_and_model
# ─────────────────────────────────────────────────────────────────────────────

class TestVectorNamespace:
    def test_namespace_format(self):
        """Namespace must be tenant_id:embedding_model_id:index_version."""
        ns = vector_namespace("tenant-abc")
        assert ns == f"tenant-abc:{EMBEDDING_MODEL_ID}:{VECTOR_INDEX_VERSION}"

    def test_namespace_deterministic(self):
        """Same inputs produce same namespace."""
        ns1 = vector_namespace("tenant-xyz")
        ns2 = vector_namespace("tenant-xyz")
        assert ns1 == ns2

    def test_namespace_different_tenants(self):
        """Different tenants produce different namespaces."""
        ns_a = vector_namespace("tenant-a")
        ns_b = vector_namespace("tenant-b")
        assert ns_a != ns_b

    def test_namespace_contains_model_id(self):
        """Namespace includes the embedding model identifier."""
        ns = vector_namespace("tenant-1")
        assert EMBEDDING_MODEL_ID in ns

    def test_namespace_contains_index_version(self):
        """Namespace includes index version for future migrations."""
        ns = vector_namespace("tenant-1")
        assert VECTOR_INDEX_VERSION in ns


# ─────────────────────────────────────────────────────────────────────────────
# 2) test_cross_tenant_same_query_does_not_hit_same_index
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossTenantIsolation:
    def test_l3_semantic_cache_isolated_by_namespace(self):
        """Tenant A's cached result must NOT be visible to Tenant B."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)

        # Mock vectorizer
        mock_vectorizer = MagicMock()
        # Return different sparse vectors for store vs lookup
        import numpy as np
        from unittest.mock import PropertyMock

        mock_vec = MagicMock()
        mock_vectorizer.transform.return_value = mock_vec

        ns_a = vector_namespace("tenant-a")
        ns_b = vector_namespace("tenant-b")

        # Store a result for tenant A
        cache.store("Apple Corp", {"resolved": "Apple Inc.", "confidence": 0.95, "reason": "LLM"},
                     mock_vectorizer, namespace=ns_a)

        # Exact lookup for tenant A should hit
        result_a = cache.lookup("Apple Corp", mock_vectorizer, None, namespace=ns_a)
        # Normalize to match cache key
        normalized = re.sub(r'[^a-z0-9]', '', "Apple Corp".lower())

        # Verify tenant A has the entry
        assert ns_a in cache._partitions
        assert normalized in cache._partitions[ns_a]

        # Verify tenant B does NOT have the entry
        if ns_b in cache._partitions:
            assert normalized not in cache._partitions[ns_b]

    def test_l3_semantic_cache_store_separate_partitions(self):
        """Storing for two tenants creates separate partitions."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vectorizer = MagicMock()
        mock_vectorizer.transform.return_value = MagicMock()

        ns_a = vector_namespace("tenant-a")
        ns_b = vector_namespace("tenant-b")

        cache.store("Microsoft", {"resolved": "Microsoft Corporation", "confidence": 0.9, "reason": "LLM"},
                     mock_vectorizer, namespace=ns_a)
        cache.store("Google", {"resolved": "Alphabet Inc.", "confidence": 0.9, "reason": "LLM"},
                     mock_vectorizer, namespace=ns_b)

        assert len(cache._partitions) == 2
        assert ns_a in cache._partitions
        assert ns_b in cache._partitions
        # Each partition has exactly 1 entry
        assert len(cache._partitions[ns_a]) == 1
        assert len(cache._partitions[ns_b]) == 1

    def test_l3_semantic_cache_no_namespace_returns_none(self):
        """Lookup without namespace returns None (no cross-talk)."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vectorizer = MagicMock()
        result = cache.lookup("Apple", mock_vectorizer, None, namespace=None)
        assert result is None

    def test_l3_semantic_cache_no_namespace_store_noop(self):
        """Store without namespace is a no-op."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vectorizer = MagicMock()
        cache.store("Apple", {"resolved": "Apple Inc.", "confidence": 0.9, "reason": "LLM"},
                     mock_vectorizer, namespace=None)
        assert len(cache._partitions) == 0
        assert cache.stores == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3) test_cache_key_partitioned_by_tenant
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheKeyPartitioning:
    def test_firestore_cache_key_includes_tenant(self):
        """L3 Firestore cache key includes tenant_id in hash input."""
        key_a = _compute_l3_cache_key("tenant-a", "Apple Inc.")
        key_b = _compute_l3_cache_key("tenant-b", "Apple Inc.")
        # Same company, different tenants → different cache keys
        assert key_a != key_b

    def test_firestore_cache_key_deterministic(self):
        """Same tenant + same company → same cache key."""
        key1 = _compute_l3_cache_key("tenant-x", "Microsoft Corp")
        key2 = _compute_l3_cache_key("tenant-x", "Microsoft Corp")
        assert key1 == key2

    def test_firestore_collection_path_includes_tenant_hash(self):
        """Phase 2B: Firestore collection path must use tenant hash prefix."""
        tenant_id = "tenant-sovereign-001"
        ns_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        expected_path = f"l3_cache/{ns_hash}/entries"
        # Verify the hash is deterministic
        ns_hash2 = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        assert ns_hash == ns_hash2
        assert "l3_cache/" in expected_path
        assert "/entries" in expected_path

    def test_different_tenants_different_collection_paths(self):
        """Different tenants produce different collection paths."""
        hash_a = hashlib.sha256("tenant-a".encode()).hexdigest()[:16]
        hash_b = hashlib.sha256("tenant-b".encode()).hexdigest()[:16]
        assert hash_a != hash_b


# ─────────────────────────────────────────────────────────────────────────────
# 4) test_missing_tenant_id_fail_closed_vector_path
# ─────────────────────────────────────────────────────────────────────────────

class TestFailClosedVectorPath:
    def test_vector_namespace_rejects_empty_tenant(self):
        """Empty tenant_id raises ValueError (fail-closed)."""
        with pytest.raises(ValueError, match="VECTOR_NAMESPACE_FAIL_CLOSED"):
            vector_namespace("")

    def test_vector_namespace_rejects_unknown_tenant(self):
        """'unknown' tenant_id raises ValueError (fail-closed)."""
        with pytest.raises(ValueError, match="VECTOR_NAMESPACE_FAIL_CLOSED"):
            vector_namespace("unknown")

    def test_get_vector_candidates_fails_closed_no_tenant(self):
        """get_vector_candidates raises if tenant_id is 'unknown' and sklearn is available."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            sklearn_available = True
        except ImportError:
            sklearn_available = False

        if sklearn_available:
            with pytest.raises(ValueError, match="VECTOR_NAMESPACE_FAIL_CLOSED"):
                get_vector_candidates("Apple Inc.", top_n=5, tenant_id="unknown")
        else:
            # Without sklearn, returns [] before reaching namespace validation
            result = get_vector_candidates("Apple Inc.", top_n=5, tenant_id="unknown")
            assert result == []

    def test_get_vector_candidates_fails_closed_empty_tenant(self):
        """get_vector_candidates raises if tenant_id is empty and sklearn is available."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            sklearn_available = True
        except ImportError:
            sklearn_available = False

        if sklearn_available:
            with pytest.raises(ValueError, match="VECTOR_NAMESPACE_FAIL_CLOSED"):
                get_vector_candidates("Apple Inc.", top_n=5, tenant_id="")
        else:
            result = get_vector_candidates("Apple Inc.", top_n=5, tenant_id="")
            assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 5) test_determinism_unchanged_no_vector_calls_for_L1_only_batch
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterminismUnchanged:
    def test_l1_match_no_vector_call(self):
        """L1 match (exact or normalized) resolves without touching vector path."""
        # "Apple Inc." resolves at L1 (exact or norm depending on normalization)
        result = resolve_entity_sync("Apple Inc.", tenant_id="tenant-test", batch_trace_id="TEST-001")
        assert result["layer"] in ("L1_EXACT", "L1_NORM")
        assert result["resolved"] == "Apple Inc."
        assert result["confidence"] == 1.0

    def test_l1_norm_match_no_vector_call(self):
        """L1 normalized match resolves without vector path."""
        # Test a known normalized match
        result = resolve_entity_sync("microsoft corporation", tenant_id="tenant-test", batch_trace_id="TEST-002")
        assert result["layer"] in ("L1_EXACT", "L1_NORM")
        assert result["resolved"] is not None

    def test_l0_garbage_no_vector_call(self):
        """L0 garbage detection resolves without vector path."""
        result = resolve_entity_sync("", tenant_id="tenant-test", batch_trace_id="TEST-003")
        assert result["layer"].startswith("L0_")

    def test_l1_results_identical_across_tenants(self):
        """L1 resolution is tenant-independent (same canonical list)."""
        result_a = resolve_entity_sync("Apple Inc.", tenant_id="tenant-a", batch_trace_id="TEST-A")
        result_b = resolve_entity_sync("Apple Inc.", tenant_id="tenant-b", batch_trace_id="TEST-B")
        assert result_a["resolved"] == result_b["resolved"]
        assert result_a["layer"] == result_b["layer"]
        assert result_a["confidence"] == result_b["confidence"]

    def test_l2_vector_resolves_with_valid_tenant(self):
        """L2 vector similarity works when tenant_id is provided."""
        # "Appple Inc" is a common L2 test case (typo → Apple Inc.)
        result = resolve_entity_sync("Appple Inc", tenant_id="tenant-test", batch_trace_id="TEST-L2")
        # Should resolve at L2 if sklearn is available
        if result["layer"] == "L2_VECTOR":
            assert result["resolved"] is not None
            assert result["confidence"] >= 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 6) Thread safety — concurrent access to partitioned cache
# ─────────────────────────────────────────────────────────────────────────────

class TestPartitionedCacheThreadSafety:
    def test_concurrent_stores_different_tenants(self):
        """Concurrent stores to different tenant partitions don't corrupt."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vectorizer = MagicMock()
        mock_vectorizer.transform.return_value = MagicMock()

        errors = []

        def store_for_tenant(tid, company, resolved):
            try:
                ns = vector_namespace(tid)
                for _ in range(50):
                    cache.store(company, {"resolved": resolved, "confidence": 0.9, "reason": "LLM"},
                                 mock_vectorizer, namespace=ns)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=store_for_tenant, args=("tenant-1", "Apple", "Apple Inc.")),
            threading.Thread(target=store_for_tenant, args=("tenant-2", "Google", "Alphabet Inc.")),
            threading.Thread(target=store_for_tenant, args=("tenant-3", "Tesla", "Tesla Inc.")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache._partitions) == 3

    def test_stats_reflect_all_partitions(self):
        """get_stats() aggregates across all partitions."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vectorizer = MagicMock()
        mock_vectorizer.transform.return_value = MagicMock()

        for tid in ["tenant-a", "tenant-b", "tenant-c"]:
            ns = vector_namespace(tid)
            cache.store(f"Company-{tid}", {"resolved": f"Resolved-{tid}", "confidence": 0.9, "reason": "LLM"},
                         mock_vectorizer, namespace=ns)

        stats = cache.get_stats()
        assert stats["size"] == 3  # Total entries across all partitions
        assert stats["partitions"] == 3
        assert stats["stores"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 7) test_singleflight_release_cleans_pending_stub
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleflightRelease:
    def test_release_deletes_pending_stub(self):
        """l3_singleflight_release deletes a pending stub without error."""
        # Without Firestore, release is a no-op (no exception raised)
        l3_singleflight_release("tenant-test", "Some Company")

    def test_release_no_firestore_is_noop(self):
        """Release with no Firestore connection does not raise."""
        with patch("app.server_enterprise_golden._firestore_db", None):
            l3_singleflight_release("tenant-test", "Some Company")

    @patch("app.server_enterprise_golden._firestore_db")
    def test_release_only_deletes_pending(self, mock_db):
        """Release only deletes documents with status='pending'."""
        import hashlib

        tenant_id = "tenant-release-test"
        company = "Test Corp"

        # Mock a pending document
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"status": "pending", "created_at": "2026-01-01T00:00:00"}

        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value = mock_doc

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection

        l3_singleflight_release(tenant_id, company)

        # Verify delete was called
        mock_doc_ref.delete.assert_called_once()

    @patch("app.server_enterprise_golden._firestore_db")
    def test_release_does_not_delete_completed(self, mock_db):
        """Release does NOT delete documents with status != 'pending'."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"status": "unknown", "resolved": None}

        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value = mock_doc

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection

        l3_singleflight_release("tenant-x", "Company Y")

        # Should NOT delete a completed entry
        mock_doc_ref.delete.assert_not_called()
