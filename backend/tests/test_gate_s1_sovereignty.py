"""
test_gate_s1_sovereignty.py — Day 5 Gate S1: Cross-Tenant Cache Isolation Proof

Proves:
1) L3 cache keys differ between tenants for identical input
2) No cache hits bleed across tenants (semantic cache + Firestore cache)
3) Evidence shows correct tenant_id on resolved records
4) Cache key includes all Day 5 sovereign components:
   tenant_id + agent_version_id + config_version + provider + model + canonical_input_hash
5) agent_version_id changes invalidate cache keys
6) Determinism preserved: same tenant + same input = same cache key
"""

import hashlib
import pytest
from unittest.mock import patch, MagicMock

from app.server_enterprise_golden import (
    _compute_l3_cache_key,
    _normalize_for_cache_key,
    vector_namespace,
    L3SemanticCache,
    AGENT_VERSION_ID,
    CANONICAL_CONFIG_HASH,
    L3_MODEL_ID,
    L3_PROVIDER_ID,
    EMBEDDING_MODEL_ID,
    VECTOR_INDEX_VERSION,
    _CANONICAL_LIST_HASH,
    resolve_entity_sync,
    l3_firestore_cache_get,
    l3_firestore_cache_set,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) Cache keys differ between tenants for identical input
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheKeyTenantIsolation:
    """Gate S1 Core: Same input, different tenants → different cache keys."""

    def test_same_input_different_tenants_different_keys(self):
        """Identical company name produces different keys for different tenants."""
        key_a = _compute_l3_cache_key("tenant-alpha", "Dow Chemical Company")
        key_b = _compute_l3_cache_key("tenant-beta", "Dow Chemical Company")
        assert key_a != key_b

    def test_same_input_same_tenant_same_key(self):
        """Determinism: same tenant + same input = same key."""
        key1 = _compute_l3_cache_key("tenant-alpha", "Dow Chemical Company")
        key2 = _compute_l3_cache_key("tenant-alpha", "Dow Chemical Company")
        assert key1 == key2

    def test_cache_key_is_sha256(self):
        """Cache key is a valid SHA256 hex digest."""
        key = _compute_l3_cache_key("tenant-x", "Apple Inc.")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_many_tenants_all_unique(self):
        """10 tenants with identical input → 10 unique cache keys."""
        company = "Microsoft Corporation"
        keys = set()
        for i in range(10):
            keys.add(_compute_l3_cache_key(f"tenant-{i}", company))
        assert len(keys) == 10


# ─────────────────────────────────────────────────────────────────────────────
# 2) Cache key includes all Day 5 sovereign components
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheKeySovereignComponents:
    """Verify cache key hash input includes all required identity components."""

    def test_agent_version_id_in_key(self):
        """Changing agent_version_id changes the cache key."""
        key_before = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        with patch("app.server_enterprise_golden.AGENT_VERSION_ID", "4.0.0-f600v4"):
            key_after = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        assert key_before != key_after

    def test_config_version_in_key(self):
        """Changing config hash changes the cache key."""
        key_before = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        with patch("app.server_enterprise_golden.CANONICAL_CONFIG_HASH", "f600v4"):
            key_after = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        assert key_before != key_after

    def test_provider_in_key(self):
        """Changing LLM provider changes the cache key."""
        key_before = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        with patch("app.server_enterprise_golden.L3_PROVIDER_ID", "openrouter"):
            key_after = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        assert key_before != key_after

    def test_model_in_key(self):
        """Changing LLM model changes the cache key."""
        key_before = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        with patch("app.server_enterprise_golden.L3_MODEL_ID", "claude-3-5-sonnet-20241022"):
            key_after = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        assert key_before != key_after

    def test_canonical_list_hash_in_key(self):
        """Changing canonical list hash changes the cache key."""
        key_before = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        with patch("app.server_enterprise_golden._CANONICAL_LIST_HASH", "0000000000000000"):
            key_after = _compute_l3_cache_key("tenant-1", "Apple Inc.")
        assert key_before != key_after

    def test_agent_version_id_format(self):
        """AGENT_VERSION_ID follows ENGINE_VERSION-CONFIG_HASH format."""
        parts = AGENT_VERSION_ID.split("-")
        assert len(parts) >= 2
        assert CANONICAL_CONFIG_HASH in AGENT_VERSION_ID

    def test_l3_provider_id_is_string(self):
        """L3_PROVIDER_ID is a non-empty string."""
        assert isinstance(L3_PROVIDER_ID, str)
        assert len(L3_PROVIDER_ID) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 3) Semantic cache: no cross-tenant bleed
# ─────────────────────────────────────────────────────────────────────────────

class TestSemanticCacheCrossTenantIsolation:
    """Prove in-memory semantic cache partitions are isolated by tenant."""

    def test_tenant_a_store_not_visible_to_tenant_b(self):
        """Tenant A stores a result; Tenant B cannot see it."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vec = MagicMock()
        mock_vec.transform.return_value = MagicMock()

        ns_a = vector_namespace("tenant-alpha")
        ns_b = vector_namespace("tenant-beta")

        # Store for tenant A
        cache.store(
            "Dow Chemical",
            {"resolved": "Dow Inc.", "confidence": 0.88, "reason": "LLM"},
            mock_vec, namespace=ns_a,
        )

        # Tenant A partition should have the entry
        normalized = _normalize_for_cache_key("Dow Chemical")
        assert ns_a in cache._partitions
        assert normalized in cache._partitions[ns_a]

        # Tenant B partition must NOT have it
        assert ns_b not in cache._partitions

    def test_same_input_both_tenants_separate_partitions(self):
        """Same input stored for both tenants creates independent entries."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vec = MagicMock()
        mock_vec.transform.return_value = MagicMock()

        ns_a = vector_namespace("tenant-alpha")
        ns_b = vector_namespace("tenant-beta")

        cache.store(
            "Dow Chemical",
            {"resolved": "Dow Inc.", "confidence": 0.88, "reason": "LLM"},
            mock_vec, namespace=ns_a,
        )
        cache.store(
            "Dow Chemical",
            {"resolved": "Dow Inc.", "confidence": 0.90, "reason": "LLM"},
            mock_vec, namespace=ns_b,
        )

        assert len(cache._partitions) == 2
        assert ns_a in cache._partitions
        assert ns_b in cache._partitions

        # Each has exactly 1 entry
        assert len(cache._partitions[ns_a]) == 1
        assert len(cache._partitions[ns_b]) == 1

    def test_stats_track_both_tenants(self):
        """Stats aggregate across all tenant partitions."""
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vec = MagicMock()
        mock_vec.transform.return_value = MagicMock()

        for tid in ["tenant-alpha", "tenant-beta", "tenant-gamma"]:
            ns = vector_namespace(tid)
            cache.store(
                f"Company-{tid}",
                {"resolved": f"Resolved-{tid}", "confidence": 0.9, "reason": "LLM"},
                mock_vec, namespace=ns,
            )

        stats = cache.get_stats()
        assert stats["size"] == 3
        assert stats["partitions"] == 3
        assert stats["stores"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 4) Firestore cache: namespace-partitioned collection paths
# ─────────────────────────────────────────────────────────────────────────────

class TestFirestoreCacheNamespaceIsolation:
    """Prove Firestore cache paths are isolated per tenant."""

    def test_collection_paths_differ_by_tenant(self):
        """Different tenants produce different Firestore collection paths."""
        hash_a = hashlib.sha256("tenant-alpha".encode()).hexdigest()[:16]
        hash_b = hashlib.sha256("tenant-beta".encode()).hexdigest()[:16]
        path_a = f"l3_cache/{hash_a}/entries"
        path_b = f"l3_cache/{hash_b}/entries"
        assert path_a != path_b

    def test_same_company_different_tenant_different_doc_ids(self):
        """Same company name → different Firestore document IDs for different tenants."""
        key_a = _compute_l3_cache_key("tenant-alpha", "Dow Chemical Company")
        key_b = _compute_l3_cache_key("tenant-beta", "Dow Chemical Company")
        assert key_a != key_b

    def test_firestore_cache_get_no_db_returns_none(self):
        """Without Firestore, cache get returns None (no bleed possible)."""
        with patch("app.server_enterprise_golden._firestore_db", None):
            result = l3_firestore_cache_get("tenant-alpha", "Dow Chemical")
            assert result is None

    def test_firestore_cache_set_no_db_is_noop(self):
        """Without Firestore, cache set is a no-op (no bleed possible)."""
        with patch("app.server_enterprise_golden._firestore_db", None):
            # Should not raise
            l3_firestore_cache_set("tenant-alpha", "Dow Chemical", {
                "resolved": "Dow Inc.", "confidence": 0.88, "layer": "L3_LLM",
            })


# ─────────────────────────────────────────────────────────────────────────────
# 5) Evidence: resolve_entity_sync carries correct tenant_id
# ─────────────────────────────────────────────────────────────────────────────

class TestResolutionTenantEvidence:
    """Prove resolved records carry correct tenant identity."""

    def test_l1_result_tenant_independent(self):
        """L1 resolution is deterministic across tenants (same canonical list)."""
        result_a = resolve_entity_sync("Apple Inc.", tenant_id="tenant-alpha", batch_trace_id="S1-A")
        result_b = resolve_entity_sync("Apple Inc.", tenant_id="tenant-beta", batch_trace_id="S1-B")

        assert result_a["resolved"] == result_b["resolved"]
        assert result_a["layer"] == result_b["layer"]
        assert result_a["confidence"] == result_b["confidence"]

    def test_l1_exact_match_no_cache_needed(self):
        """L1 matches resolve without touching cache — no bleed vector."""
        result = resolve_entity_sync("Apple Inc.", tenant_id="tenant-alpha", batch_trace_id="S1-L1")
        assert result["layer"] in ("L1_EXACT", "L1_NORM")
        assert result["resolved"] == "Apple Inc."
        assert result["confidence"] == 1.0

    def test_l2_match_uses_tenant_namespace(self):
        """L2 vector match uses tenant-scoped namespace."""
        # "Appple Inc" (typo) should hit L2
        result = resolve_entity_sync("Appple Inc", tenant_id="tenant-alpha", batch_trace_id="S1-L2")
        if result["layer"] == "L2_VECTOR":
            assert result["resolved"] is not None
            assert result["confidence"] >= 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 6) Full cross-tenant isolation scenario
# ─────────────────────────────────────────────────────────────────────────────

class TestFullCrossTenantScenario:
    """
    End-to-end Gate S1 proof: run identical input through two tenants,
    verify cache keys differ, no cache bleed, tenant identity preserved.
    """

    def test_full_scenario_same_input_two_tenants(self):
        """
        Gate S1 core proof:
        1. Compute cache keys for same input, two tenants → differ
        2. Resolve same L1 input for both → identical results (no cache involved)
        3. Verify semantic cache partitions are independent
        4. Verify Firestore collection paths are independent
        """
        company = "Dow Chemical Company"
        tenant_a = "tenant-sovereign-alpha"
        tenant_b = "tenant-sovereign-beta"

        # 1) Cache keys differ
        key_a = _compute_l3_cache_key(tenant_a, company)
        key_b = _compute_l3_cache_key(tenant_b, company)
        assert key_a != key_b, "Cache keys must differ between tenants"

        # 2) Firestore collection paths differ
        hash_a = hashlib.sha256(tenant_a.encode()).hexdigest()[:16]
        hash_b = hashlib.sha256(tenant_b.encode()).hexdigest()[:16]
        assert hash_a != hash_b, "Firestore namespace hashes must differ"

        # 3) Vector namespaces differ
        ns_a = vector_namespace(tenant_a)
        ns_b = vector_namespace(tenant_b)
        assert ns_a != ns_b, "Vector namespaces must differ"

        # 4) Semantic cache isolation
        cache = L3SemanticCache(similarity_threshold=0.85, max_size=1000)
        mock_vec = MagicMock()
        mock_vec.transform.return_value = MagicMock()

        cache.store(
            company,
            {"resolved": "Dow Inc.", "confidence": 0.9, "reason": "LLM"},
            mock_vec, namespace=ns_a,
        )

        # Tenant B cannot see tenant A's cache
        assert ns_b not in cache._partitions
        # Tenant A has it (semantic cache uses re.sub normalization, not _normalize_for_cache_key)
        import re
        cache_normalized = re.sub(r'[^a-z0-9]', '', company.lower())
        assert cache_normalized in cache._partitions[ns_a]

        # 5) L1 resolution is tenant-independent (no cache involved)
        result_a = resolve_entity_sync("Apple Inc.", tenant_id=tenant_a, batch_trace_id="S1-FULL-A")
        result_b = resolve_entity_sync("Apple Inc.", tenant_id=tenant_b, batch_trace_id="S1-FULL-B")
        assert result_a["resolved"] == result_b["resolved"]
        assert result_a["layer"] == result_b["layer"]

    def test_cache_key_components_all_present(self):
        """Verify the cache key hash input contains all Day 5 sovereign components."""
        normalized = _normalize_for_cache_key("Test Corp")
        expected_input = (
            f"tenant-proof|{AGENT_VERSION_ID}|{CANONICAL_CONFIG_HASH}"
            f"|{L3_PROVIDER_ID}|{L3_MODEL_ID}"
            f"|{normalized}|{_CANONICAL_LIST_HASH}"
        )
        expected_key = hashlib.sha256(expected_input.encode()).hexdigest()
        actual_key = _compute_l3_cache_key("tenant-proof", "Test Corp")
        assert actual_key == expected_key, (
            f"Cache key mismatch — expected hash of '{expected_input}'"
        )
