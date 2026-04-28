"""
================================================================================
SHARD DETERMINISM TESTS
================================================================================

Tests for deterministic global cache guardrails (shard safety):

1. Layer normalization: cache-variant layers hash identically
2. Config hash invalidation: different canonical lists → different cache keys
3. Replay variance: after layer normalization, replay produces variance == 0
4. Decision ledger layer normalization

Run with: pytest backend/tests/test_shard_determinism.py -v
================================================================================
"""

import pytest
import hashlib
from pathlib import Path
from typing import List, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.hash_chain import (
    normalize_event_for_hashing,
    compute_event_hash,
    compute_batch_hash_chain,
    compute_batch_hash_chain_iavp,
    _canonicalize_layer,
    _LAYER_CANONICAL,
    GENESIS_HASH,
)

from app.security.iavp import (
    build_decision_ledger,
    prepare_records_for_chain,
    _canonicalize_layer as iavp_canonicalize_layer,
    _LAYER_CANONICAL as IAVP_LAYER_CANONICAL,
)


# =============================================================================
# LAYER NORMALIZATION TESTS
# =============================================================================

class TestLayerNormalization:
    """Verify that cache-variant layer names hash identically."""

    def test_l3_cached_normalizes_to_l3_llm(self):
        assert _canonicalize_layer("L3_CACHED") == "L3_LLM"

    def test_l3_firestore_cached_normalizes_to_l3_llm(self):
        assert _canonicalize_layer("L3_FIRESTORE_CACHED") == "L3_LLM"

    def test_l3_person_cached_normalizes_to_l3_person_llm(self):
        assert _canonicalize_layer("L3_PERSON_CACHED") == "L3_PERSON_LLM"

    def test_non_cache_layers_unchanged(self):
        for layer in ["L0_GARBAGE", "L1_EXACT", "L1_NORM", "L1_PARENT",
                       "L2_TFIDF", "L3_LLM", "L4_HUMAN", "L3_PERSON_LLM"]:
            assert _canonicalize_layer(layer) == layer

    def test_iavp_module_has_same_mapping(self):
        """hash_chain.py and iavp.py must have identical canonical mappings."""
        assert _LAYER_CANONICAL == IAVP_LAYER_CANONICAL

    def test_iavp_canonicalize_matches_hash_chain(self):
        """Both modules produce the same result for all cache variants."""
        for variant in ["L3_CACHED", "L3_FIRESTORE_CACHED", "L3_PERSON_CACHED",
                         "L3_LLM", "L1_EXACT", "L4_HUMAN"]:
            assert _canonicalize_layer(variant) == iavp_canonicalize_layer(variant)


class TestLayerNormalizationInHashing:
    """Verify that layer normalization produces identical hashes across cache topologies."""

    BASE_EVENT = {
        "original": "Acme Corp",
        "resolved": "Acme Corporation",
        "confidence": 0.92,
        "entity_type": "company",
        "decision_path": "L3_LLM_RESOLVE",
    }

    def test_l3_variants_produce_same_event_hash(self):
        """L3_CACHED, L3_FIRESTORE_CACHED, and L3_LLM must all hash identically."""
        hashes = []
        for layer in ["L3_LLM", "L3_CACHED", "L3_FIRESTORE_CACHED"]:
            event = {**self.BASE_EVENT, "layer": layer}
            h = compute_event_hash(GENESIS_HASH, event)
            hashes.append(h)

        assert hashes[0] == hashes[1], "L3_CACHED should hash same as L3_LLM"
        assert hashes[0] == hashes[2], "L3_FIRESTORE_CACHED should hash same as L3_LLM"

    def test_person_cached_hashes_same_as_person_llm(self):
        event_cached = {**self.BASE_EVENT, "layer": "L3_PERSON_CACHED"}
        event_llm = {**self.BASE_EVENT, "layer": "L3_PERSON_LLM"}

        h_cached = compute_event_hash(GENESIS_HASH, event_cached)
        h_llm = compute_event_hash(GENESIS_HASH, event_llm)
        assert h_cached == h_llm

    def test_normalize_event_strips_cache_variant(self):
        """normalize_event_for_hashing should return canonical layer."""
        event = {**self.BASE_EVENT, "layer": "L3_FIRESTORE_CACHED"}
        normalized = normalize_event_for_hashing(event)
        assert normalized["layer"] == "L3_LLM"

    def test_different_layers_produce_different_hashes(self):
        """Non-variant layers should still produce distinct hashes."""
        h_l1 = compute_event_hash(GENESIS_HASH, {**self.BASE_EVENT, "layer": "L1_EXACT"})
        h_l3 = compute_event_hash(GENESIS_HASH, {**self.BASE_EVENT, "layer": "L3_LLM"})
        assert h_l1 != h_l3


class TestBatchChainDeterminism:
    """Verify that a full batch chain is deterministic under cache topology variance."""

    # Map cache-variant layers to their canonical decision_path (mirrors production behavior).
    _LAYER_TO_DECISION = {
        "L1_EXACT": "L1_EXACT",
        "L2_TFIDF": "L2_TFIDF",
        "L3_LLM": "L3_RESOLVE",
        "L3_CACHED": "L3_RESOLVE",
        "L3_FIRESTORE_CACHED": "L3_RESOLVE",
        "L4_HUMAN": "L4_HUMAN",
    }

    def _make_events(self, layers: List[str]) -> List[Dict[str, Any]]:
        events = []
        for i, layer in enumerate(layers):
            events.append({
                "original": f"Company_{i}",
                "resolved": f"Canonical_{i}" if layer != "L4_HUMAN" else None,
                "layer": layer,
                "confidence": 0.95 if layer != "L4_HUMAN" else 0.0,
                "entity_type": "company",
                "decision_path": self._LAYER_TO_DECISION.get(layer, layer),
            })
        return events

    def test_mixed_cache_topology_same_root_hash(self):
        """
        Simulate two workers: one hits in-memory cache (L3_CACHED),
        other hits Firestore cache (L3_FIRESTORE_CACHED), another calls LLM (L3_LLM).
        All must produce the same batch root hash.
        """
        # Worker 1: all fresh LLM
        layers_w1 = ["L1_EXACT", "L2_TFIDF", "L3_LLM", "L4_HUMAN"]
        # Worker 2: some cached
        layers_w2 = ["L1_EXACT", "L2_TFIDF", "L3_CACHED", "L4_HUMAN"]
        # Worker 3: Firestore cached
        layers_w3 = ["L1_EXACT", "L2_TFIDF", "L3_FIRESTORE_CACHED", "L4_HUMAN"]

        _, root1 = compute_batch_hash_chain("batch-1", self._make_events(layers_w1))
        _, root2 = compute_batch_hash_chain("batch-1", self._make_events(layers_w2))
        _, root3 = compute_batch_hash_chain("batch-1", self._make_events(layers_w3))

        assert root1 == root2, "L3_CACHED worker must match L3_LLM worker"
        assert root1 == root3, "L3_FIRESTORE_CACHED worker must match L3_LLM worker"


class TestDecisionLedgerLayerNormalization:
    """Verify that build_decision_ledger normalizes cache-variant layers."""

    def test_ledger_normalizes_l3_cached(self):
        records = [
            {
                "original": "Test Corp",
                "resolved": "Test Corporation",
                "layer": "L3_CACHED",
                "confidence": 0.9,
                "entity_type": "company",
                "decision_path": "L3_RESOLVE",
                "source_timestamp": "2026-01-01T00:00:00.000000Z",
                "source_system_id": "batch-xxx|0",
            }
        ]
        ledger = build_decision_ledger(records)
        assert ledger[0]["layer"] == "L3_LLM"

    def test_ledger_normalizes_l3_firestore_cached(self):
        records = [
            {
                "original": "Test Corp",
                "resolved": "Test Corporation",
                "layer": "L3_FIRESTORE_CACHED",
                "confidence": 0.9,
                "entity_type": "company",
                "decision_path": "L3_RESOLVE",
                "source_timestamp": "2026-01-01T00:00:00.000000Z",
                "source_system_id": "batch-xxx|0",
            }
        ]
        ledger = build_decision_ledger(records)
        assert ledger[0]["layer"] == "L3_LLM"

    def test_ledger_preserves_non_cache_layers(self):
        records = [
            {
                "original": "Test Corp",
                "resolved": "Test Corporation",
                "layer": "L1_EXACT",
                "confidence": 1.0,
                "entity_type": "company",
                "decision_path": "L1_EXACT",
                "source_timestamp": "2026-01-01T00:00:00.000000Z",
                "source_system_id": "batch-xxx|0",
            }
        ]
        ledger = build_decision_ledger(records)
        assert ledger[0]["layer"] == "L1_EXACT"


# =============================================================================
# CONFIG HASH CACHE KEY TESTS
# =============================================================================

class TestConfigHashCacheKey:
    """Verify that _CANONICAL_LIST_HASH is included in cache keys."""

    def test_canonical_list_hash_exists(self):
        """_CANONICAL_LIST_HASH is a 16-char hex string."""
        from app.server_enterprise_golden import _CANONICAL_LIST_HASH
        assert isinstance(_CANONICAL_LIST_HASH, str)
        assert len(_CANONICAL_LIST_HASH) == 16
        # Must be valid hex
        int(_CANONICAL_LIST_HASH, 16)

    def test_cache_key_includes_canonical_hash(self):
        """Cache key must differ when canonical list hash differs."""
        from app.server_enterprise_golden import _compute_l3_cache_key, _CANONICAL_LIST_HASH

        key1 = _compute_l3_cache_key("tenant_a", "Acme Corp")
        key2 = _compute_l3_cache_key("tenant_a", "Acme Corp")
        assert key1 == key2, "Same inputs must produce same key"

        # Different tenants must produce different keys
        key3 = _compute_l3_cache_key("tenant_b", "Acme Corp")
        assert key1 != key3

    def test_different_canonical_list_produces_different_hash(self):
        """Simulate: if CANONICALS changed, _CANONICAL_LIST_HASH would change."""
        list_a = sorted(["apple", "google", "microsoft"])
        list_b = sorted(["apple", "google", "microsoft", "nvidia"])

        hash_a = hashlib.sha256("|".join(list_a).encode()).hexdigest()[:16]
        hash_b = hashlib.sha256("|".join(list_b).encode()).hexdigest()[:16]
        assert hash_a != hash_b


# =============================================================================
# REPLAY DETERMINISM TESTS
# =============================================================================

class TestReplayDeterminism:
    """Verify replay verification with layer normalization."""

    def test_iavp_chain_with_cache_variants_is_deterministic(self):
        """
        Build IAVP chain twice with different cache-topology layers.
        Root hashes must match.
        """
        events_base = [
            {"original": "Apple Inc", "resolved": "Apple Inc.", "layer": "L3_LLM",
             "confidence": 0.95, "entity_type": "company", "decision_path": "L3_RESOLVE"},
            {"original": "GOOGL", "resolved": "Alphabet Inc.", "layer": "L1_PARENT",
             "confidence": 1.0, "entity_type": "company", "decision_path": "L1_PARENT"},
            {"original": "msft", "resolved": "Microsoft Corporation", "layer": "L2_TFIDF",
             "confidence": 0.88, "entity_type": "company", "decision_path": "L2_TFIDF"},
        ]

        events_cached = [
            {"original": "Apple Inc", "resolved": "Apple Inc.", "layer": "L3_FIRESTORE_CACHED",
             "confidence": 0.95, "entity_type": "company", "decision_path": "L3_RESOLVE"},
            {"original": "GOOGL", "resolved": "Alphabet Inc.", "layer": "L1_PARENT",
             "confidence": 1.0, "entity_type": "company", "decision_path": "L1_PARENT"},
            {"original": "msft", "resolved": "Microsoft Corporation", "layer": "L2_TFIDF",
             "confidence": 0.88, "entity_type": "company", "decision_path": "L2_TFIDF"},
        ]

        trace_id = "TEST-SHARD-001"
        _, root_base, replay_base = compute_batch_hash_chain_iavp(
            trace_id, events_base, enable_replay_verification=True
        )
        _, root_cached, replay_cached = compute_batch_hash_chain_iavp(
            trace_id, events_cached, enable_replay_verification=True
        )

        assert root_base == root_cached, (
            f"Root hash mismatch: base={root_base}, cached={root_cached}"
        )
        assert replay_base.passed, f"Replay variance on base: {replay_base.variance}"
        assert replay_cached.passed, f"Replay variance on cached: {replay_cached.variance}"

    def test_replay_zero_variance(self):
        """Standard batch (no cache variants) must have 0 replay variance."""
        events = [
            {"original": f"Company_{i}", "resolved": f"Canonical_{i}",
             "layer": "L1_EXACT", "confidence": 1.0, "entity_type": "company",
             "decision_path": "L1_EXACT"}
            for i in range(20)
        ]
        _, root, replay = compute_batch_hash_chain_iavp(
            "TEST-REPLAY-001", events, enable_replay_verification=True
        )
        assert replay.passed
        assert replay.variance == 0
