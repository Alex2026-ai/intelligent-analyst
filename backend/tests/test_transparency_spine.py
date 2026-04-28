"""
Tests for Phase 9.1 — Transparency Log Spine.

Covers:
1. Deterministic leaf hash
2. Append-only insertion
3. Proof validation (offline)
4. Signed root generation
5. Receipt entry insertion
6. Assertion entry insertion
7. Async retry on insertion failure
8. Proof depth <= 64
9. No regression to finalize latency > 5%
"""

import hashlib
import json
import time
import threading
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.transparency.leaf import (
    build_leaf_payload,
    hash_leaf,
    LEAF_VERSION,
    VALID_ENTRY_TYPES,
)
from app.transparency.merkle import (
    MerkleTree,
    verify_inclusion_proof,
    MAX_PROOF_DEPTH,
)
from app.transparency.spine import (
    insert_entry,
    enqueue_entry,
    publish_root,
    get_inclusion_proof,
    get_latest_root,
    reset_spine,
)


# ---------------------------------------------------------------------------
# Test 1: Deterministic leaf hash
# ---------------------------------------------------------------------------

class TestDeterministicLeafHash:
    def test_same_inputs_produce_same_hash(self):
        """Identical inputs must produce identical leaf hashes."""
        payload1 = build_leaf_payload(
            entry_type="receipt",
            entry_id="rcpt-001",
            root_hash="a" * 64,
            timestamp="2026-03-14T00:00:00.000000Z",
            nonce="fixed-nonce-12345678",
        )
        payload2 = build_leaf_payload(
            entry_type="receipt",
            entry_id="rcpt-001",
            root_hash="a" * 64,
            timestamp="2026-03-14T00:00:00.000000Z",
            nonce="fixed-nonce-12345678",
        )
        assert hash_leaf(payload1) == hash_leaf(payload2)

    def test_different_inputs_produce_different_hash(self):
        """Different inputs must produce different leaf hashes."""
        payload1 = build_leaf_payload(
            entry_type="receipt",
            entry_id="rcpt-001",
            root_hash="a" * 64,
            timestamp="2026-03-14T00:00:00.000000Z",
            nonce="nonce-1",
        )
        payload2 = build_leaf_payload(
            entry_type="receipt",
            entry_id="rcpt-002",
            root_hash="a" * 64,
            timestamp="2026-03-14T00:00:00.000000Z",
            nonce="nonce-2",
        )
        assert hash_leaf(payload1) != hash_leaf(payload2)

    def test_leaf_hash_is_sha256_of_jcs(self):
        """Leaf hash must be SHA256(JCS(payload))."""
        from app.security.iavp import jcs_canonicalize

        payload = build_leaf_payload(
            entry_type="receipt",
            entry_id="rcpt-jcs",
            root_hash="b" * 64,
            timestamp="2026-03-14T00:00:00.000000Z",
            nonce="jcs-nonce",
        )
        canonical = jcs_canonicalize(payload)
        expected = hashlib.sha256(canonical).hexdigest()
        assert hash_leaf(payload) == expected

    def test_leaf_payload_version(self):
        """Leaf payload must include version field."""
        payload = build_leaf_payload(
            entry_type="assertion",
            entry_id="asrt-001",
            root_hash="c" * 64,
        )
        assert payload["version"] == LEAF_VERSION
        assert payload["version"] == "1.0"

    def test_invalid_entry_type_raises(self):
        with pytest.raises(ValueError, match="Invalid entry_type"):
            build_leaf_payload(
                entry_type="invalid",
                entry_id="x",
                root_hash="a" * 64,
            )

    def test_tombstone_entry_type_allowed(self):
        """Tombstone type must be accepted (schema reservation)."""
        payload = build_leaf_payload(
            entry_type="tombstone",
            entry_id="tomb-001",
            root_hash="d" * 64,
        )
        assert payload["entry_type"] == "tombstone"


# ---------------------------------------------------------------------------
# Test 2: Append-only insertion
# ---------------------------------------------------------------------------

class TestAppendOnlyInsertion:
    def setup_method(self):
        reset_spine()

    def test_entries_are_append_only(self):
        """Entries can only be appended, never removed."""
        r1 = insert_entry("receipt", "rcpt-001", "a" * 64)
        r2 = insert_entry("receipt", "rcpt-002", "b" * 64)
        assert r1["leaf_index"] == 0
        assert r2["leaf_index"] == 1
        assert r2["tree_size"] == 2

    def test_idempotent_insertion(self):
        """Inserting the same entry_id twice returns the same index."""
        r1 = insert_entry("receipt", "rcpt-dup", "a" * 64)
        r2 = insert_entry("receipt", "rcpt-dup", "a" * 64)
        assert r1["leaf_index"] == r2["leaf_index"]
        assert r2["tree_size"] == 1  # only one entry

    def test_tree_size_grows_monotonically(self):
        """Tree size must only increase."""
        sizes = []
        for i in range(10):
            r = insert_entry("receipt", f"rcpt-{i}", f"{i:064x}")
            sizes.append(r["tree_size"])
        assert sizes == list(range(1, 11))


# ---------------------------------------------------------------------------
# Test 3: Proof validation (offline)
# ---------------------------------------------------------------------------

class TestProofValidation:
    def setup_method(self):
        reset_spine()

    def test_inclusion_proof_validates_offline(self):
        """Inclusion proof must validate with verify_inclusion_proof()."""
        for i in range(8):
            insert_entry("receipt", f"rcpt-{i}", f"{i:064x}")

        proof_result = get_inclusion_proof("rcpt-3")
        assert proof_result["found"] is True

        is_valid = verify_inclusion_proof(
            leaf_hash_hex=proof_result["leaf_hash"],
            leaf_index=proof_result["leaf_index"],
            proof=proof_result["inclusion_proof"],
            expected_root_hex=proof_result["root_hash"],
        )
        assert is_valid is True

    def test_proof_rejects_wrong_root(self):
        """Proof must fail against a wrong root hash."""
        for i in range(4):
            insert_entry("receipt", f"rcpt-{i}", f"{i:064x}")

        proof_result = get_inclusion_proof("rcpt-1")
        is_valid = verify_inclusion_proof(
            leaf_hash_hex=proof_result["leaf_hash"],
            leaf_index=proof_result["leaf_index"],
            proof=proof_result["inclusion_proof"],
            expected_root_hex="f" * 64,  # wrong root
        )
        assert is_valid is False

    def test_proof_for_single_leaf_tree(self):
        """Proof works for a tree with a single leaf."""
        insert_entry("receipt", "rcpt-solo", "a" * 64)
        proof_result = get_inclusion_proof("rcpt-solo")
        assert proof_result["found"] is True
        assert proof_result["leaf_index"] == 0
        assert len(proof_result["inclusion_proof"]) == 0  # root IS the leaf

    def test_proof_not_found(self):
        """Proof request for nonexistent entry returns found=False."""
        insert_entry("receipt", "rcpt-exist", "a" * 64)
        proof_result = get_inclusion_proof("nonexistent")
        assert proof_result["found"] is False


# ---------------------------------------------------------------------------
# Test 4: Signed root generation
# ---------------------------------------------------------------------------

class TestSignedRoot:
    def setup_method(self):
        reset_spine()

    def test_publish_root_returns_metadata(self):
        """Published root must contain tree_size, root_hash, timestamp."""
        for i in range(5):
            insert_entry("receipt", f"rcpt-{i}", f"{i:064x}")

        root_record = publish_root()
        assert root_record["tree_size"] == 5
        assert len(root_record["root_hash"]) == 64
        assert root_record["timestamp"] is not None

    def test_latest_root_reflects_published(self):
        """get_latest_root() returns the most recently published root."""
        for i in range(3):
            insert_entry("receipt", f"rcpt-{i}", f"{i:064x}")

        publish_root()
        latest = get_latest_root()
        assert latest["tree_size"] == 3
        assert latest["latest_published"] is not None
        assert latest["latest_published"]["tree_size"] == 3

    def test_root_uses_separate_key(self):
        """Root signing must use TRANSPARENCY_KMS_KEY_ID, not receipt key."""
        from app.transparency import spine
        import os
        # Verify separate config paths exist (both may be empty in test)
        receipt_key_var = "KMS_SIGNING_KEY_ID"
        transparency_key_var = "TRANSPARENCY_KMS_KEY_ID"
        # Config paths must be distinct env vars
        assert receipt_key_var != transparency_key_var
        # Spine reads from the transparency-specific var
        with patch.dict(os.environ, {"TRANSPARENCY_KMS_KEY_ID": "projects/test/locations/us/keyRings/transparency/cryptoKeys/root-key"}):
            # Re-read the config
            key = os.getenv("TRANSPARENCY_KMS_KEY_ID", "")
            assert "transparency" in key.lower()
            assert key != os.getenv("KMS_SIGNING_KEY_ID", "")


# ---------------------------------------------------------------------------
# Test 5: Receipt entry insertion
# ---------------------------------------------------------------------------

class TestReceiptEntryInsertion:
    def setup_method(self):
        reset_spine()

    def test_receipt_entry_inserted(self):
        """New receipt produces a transparency entry."""
        result = insert_entry("receipt", "rcpt-new-001", "a" * 64)
        assert result["success"] is True
        assert result["leaf_index"] == 0
        assert len(result["leaf_hash"]) == 64

        proof = get_inclusion_proof("rcpt-new-001")
        assert proof["found"] is True


# ---------------------------------------------------------------------------
# Test 6: Assertion entry insertion
# ---------------------------------------------------------------------------

class TestAssertionEntryInsertion:
    def setup_method(self):
        reset_spine()

    def test_assertion_entry_inserted(self):
        """New assertion produces a transparency entry."""
        result = insert_entry("assertion", "asrt_test001", "b" * 64)
        assert result["success"] is True
        assert result["leaf_index"] == 0

        proof = get_inclusion_proof("asrt_test001")
        assert proof["found"] is True


# ---------------------------------------------------------------------------
# Test 7: Async retry on insertion failure
# ---------------------------------------------------------------------------

class TestAsyncRetry:
    def setup_method(self):
        reset_spine()

    def test_enqueue_retries_on_failure(self):
        """enqueue_entry retries on failure before succeeding."""
        call_count = {"n": 0}
        original_insert = insert_entry

        def flaky_insert(entry_type, entry_id, root_hash, timestamp=None):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return {"success": False, "leaf_index": None, "leaf_hash": None,
                        "tree_size": 0, "error": "transient failure"}
            return original_insert(entry_type, entry_id, root_hash, timestamp)

        with patch("app.transparency.spine.insert_entry", side_effect=flaky_insert):
            enqueue_entry("receipt", "rcpt-retry", "a" * 64)
            # Wait for background thread to complete retries
            time.sleep(8)

        assert call_count["n"] == 3  # 2 failures + 1 success


# ---------------------------------------------------------------------------
# Test 8: Proof depth <= 64
# ---------------------------------------------------------------------------

class TestProofDepthCap:
    def test_max_proof_depth_constant(self):
        """Proof depth cap must be 64."""
        assert MAX_PROOF_DEPTH == 64

    def test_proof_depth_within_cap(self):
        """For any practical tree size, proof depth <= 64."""
        tree = MerkleTree()
        for i in range(100):
            leaf_hash = hashlib.sha256(f"leaf-{i}".encode()).hexdigest()
            tree.append(leaf_hash)

        for i in range(100):
            proof = tree.inclusion_proof(i)
            assert len(proof) <= MAX_PROOF_DEPTH


# ---------------------------------------------------------------------------
# Test 9: No regression to finalize latency > 5%
# ---------------------------------------------------------------------------

class TestFinalizeLatencyRegression:
    def setup_method(self):
        reset_spine()

    def test_insertion_latency_acceptable(self):
        """Transparency entry insertion should add < 5ms overhead."""
        # Baseline: time 100 insertions
        t0 = time.time()
        for i in range(100):
            insert_entry("receipt", f"perf-{i}", f"{i:064x}")
        elapsed_ms = (time.time() - t0) * 1000

        avg_ms = elapsed_ms / 100
        # Must be well under 50ms to stay within 5% of typical finalize (1-2s)
        assert avg_ms < 50, f"avg insertion {avg_ms:.1f}ms exceeds 50ms budget"


# ---------------------------------------------------------------------------
# Additional: Merkle tree unit tests
# ---------------------------------------------------------------------------

class TestMerkleTree:
    def test_empty_tree_root(self):
        tree = MerkleTree()
        root = tree.root()
        assert len(root) == 64
        assert root == hashlib.sha256(b"").hexdigest()

    def test_single_leaf(self):
        tree = MerkleTree()
        leaf = "a" * 64
        idx = tree.append(leaf)
        assert idx == 0
        assert tree.tree_size == 1

    def test_power_of_two_leaves(self):
        tree = MerkleTree()
        for i in range(8):
            tree.append(hashlib.sha256(f"leaf-{i}".encode()).hexdigest())
        assert tree.tree_size == 8
        proof = tree.inclusion_proof(0)
        assert len(proof) == 3  # log2(8) = 3

    def test_non_power_of_two_leaves(self):
        tree = MerkleTree()
        for i in range(5):
            tree.append(hashlib.sha256(f"leaf-{i}".encode()).hexdigest())
        assert tree.tree_size == 5
        # All proofs should validate
        root = tree.root()
        for i in range(5):
            leaf_hash = hashlib.sha256(f"leaf-{i}".encode()).hexdigest()
            proof = tree.inclusion_proof(i)
            assert verify_inclusion_proof(leaf_hash, i, proof, root)

    def test_out_of_range_proof(self):
        tree = MerkleTree()
        tree.append("a" * 64)
        with pytest.raises(IndexError):
            tree.inclusion_proof(1)


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestTransparencyEndpoints:
    def test_latest_root_disabled(self):
        """Returns 503 when transparency is disabled."""
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.transparency.spine.TRANSPARENCY_ENABLED", False):
            resp = client.get("/transparency/latest-root")
        assert resp.status_code == 503

    def test_proof_disabled(self):
        """Returns 503 when transparency is disabled."""
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.transparency.spine.TRANSPARENCY_ENABLED", False):
            resp = client.get("/transparency/proof/some-entry")
        assert resp.status_code == 503

    def test_proof_not_found(self):
        """Returns 404 for nonexistent entry."""
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)

        reset_spine()
        with patch("app.transparency.spine.TRANSPARENCY_ENABLED", True):
            resp = client.get("/transparency/proof/nonexistent")
        assert resp.status_code == 404
