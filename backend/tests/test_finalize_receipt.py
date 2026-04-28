"""
Tests for receipt integration in the finalization path.

Phase 1B coverage:
- precondition guard (HMAC_SCOPE_KEY missing → fail closed)
- receipt pointer shape in batch doc
- deterministic receipt_id from batch_id + root_hash
- no dual-signing (single manifest signature)
"""

import hashlib
import os

import pytest

os.environ.setdefault("HMAC_SCOPE_KEY", "aa" * 32)

from app.attestation.receipt_paths import deterministic_receipt_id
from app.attestation.manifest_v1 import build_attestation_manifest_v1
from app.attestation.receipt_writer import build_firestore_receipt_pointer
from app.utils.hashing import compute_dataset_hash_v1, compute_tenant_scope
from app.security.iavp import jcs_canonicalize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SCOPE_KEY = bytes.fromhex("bb" * 32)

VALID_ANCHOR_REF = {
    "anchor_hash": "a" * 64,
    "anchor_timestamp": "2026-03-13T00:00:00.000000Z",
    "bucket": "ia-anchor-test",
    "object_path": "anchors/abc123/BATCH-FIN001.json",
}

VALID_METRICS = {
    "l1_pct": 0.85,
    "l2_pct": 0.08,
    "l3_pct": 0.02,
    "l4_pct": 0.05,
    "record_count": 2000,
    "replay_method": "STABLE_INPUT_ORDER_V2",
    "replay_runs": 3,
    "replay_variance": 0,
}


def _make_test_manifest(batch_id="BATCH-FIN001", root_hash="c" * 64):
    tenant_scope = compute_tenant_scope("tenant_test", scope_key=TEST_SCOPE_KEY)
    receipt_id = deterministic_receipt_id(batch_id, root_hash)
    return build_attestation_manifest_v1(
        batch_id=batch_id,
        root_hash=root_hash,
        artifact_mode="PRODUCTION_REAL",
        engine_version="8.2.2",
        environment="prod",
        config_hash="d" * 64,
        dataset_hash="e" * 64,
        registry_hash="f" * 64,
        key_id="projects/test/locations/us/keyRings/kr/cryptoKeys/k/cryptoKeyVersions/1",
        metrics=VALID_METRICS,
        tenant_scope=tenant_scope,
        anchor_ref=VALID_ANCHOR_REF,
        artifact_hashes=[],
        receipt_id=receipt_id,
    )


# ---------------------------------------------------------------------------
# Precondition guard
# ---------------------------------------------------------------------------

class TestPreconditionGuard:

    def test_hmac_key_missing_blocks_tenant_scope(self):
        """Without HMAC_SCOPE_KEY, compute_tenant_scope must fail."""
        old = os.environ.pop("HMAC_SCOPE_KEY", None)
        try:
            with pytest.raises(ValueError, match="HMAC_SCOPE_KEY"):
                compute_tenant_scope("tenant_any")
        finally:
            if old is not None:
                os.environ["HMAC_SCOPE_KEY"] = old
            else:
                os.environ["HMAC_SCOPE_KEY"] = "aa" * 32


# ---------------------------------------------------------------------------
# Deterministic receipt_id in finalize context
# ---------------------------------------------------------------------------

class TestFinalizeReceiptId:

    def test_same_batch_same_hash_same_receipt(self):
        """Retry of same finalize produces same receipt_id."""
        r1 = deterministic_receipt_id("BATCH-FIN001", "c" * 64)
        r2 = deterministic_receipt_id("BATCH-FIN001", "c" * 64)
        assert r1 == r2

    def test_different_root_hash_different_receipt(self):
        """If hash chain changes (shouldn't happen), receipt_id changes."""
        r1 = deterministic_receipt_id("BATCH-FIN001", "c" * 64)
        r2 = deterministic_receipt_id("BATCH-FIN001", "d" * 64)
        assert r1 != r2


# ---------------------------------------------------------------------------
# Receipt pointer shape
# ---------------------------------------------------------------------------

class TestReceiptPointerInBatchDoc:

    def test_pointer_has_correct_fields(self):
        ptr = build_firestore_receipt_pointer(
            receipt_id="r-001",
            gcs_prefix="gs://ia-test-receipts-us/receipts/scope/r-001",
        )
        assert set(ptr.keys()) == {"id", "gcs_path", "version", "finalized_at"}
        assert ptr["version"] == "ia-attestation/v1"

    def test_pointer_is_lightweight(self):
        """Pointer must NOT contain manifest, signature, or full attestation data."""
        ptr = build_firestore_receipt_pointer("r-001", "gs://b/p")
        assert "signature_b64" not in str(ptr)
        assert "manifest_hash" not in str(ptr)
        assert "signed_payload" not in str(ptr)
        # Only allowed keys
        assert set(ptr.keys()) == {"id", "gcs_path", "version", "finalized_at"}


# ---------------------------------------------------------------------------
# Single signing (no dual-sign)
# ---------------------------------------------------------------------------

class TestSingleSigning:

    def test_manifest_produces_single_signable_digest(self):
        """The manifest JCS bytes produce exactly one digest to sign."""
        m = _make_test_manifest()
        canonical = jcs_canonicalize(m)
        digest = hashlib.sha256(canonical).hexdigest()

        # Same manifest → same digest (deterministic, single signing input)
        canonical2 = jcs_canonicalize(m)
        digest2 = hashlib.sha256(canonical2).hexdigest()
        assert digest == digest2

    def test_manifest_does_not_contain_signature(self):
        """Manifest must NOT embed a signature field (detached model)."""
        m = _make_test_manifest()
        assert "signature" not in m
        assert "signature_b64" not in m


# ---------------------------------------------------------------------------
# Sharded finalize produces receipt bundle + pointer
# ---------------------------------------------------------------------------

class TestShardedFinalizeReceipt:

    def test_end_to_end_manifest_to_pointer(self):
        """Full flow: build manifest → JCS → receipt_id → pointer."""
        batch_id = "BATCH-SHARD1"
        root_hash = "abc123" + "0" * 58

        # Step 1: dataset hash
        records = [
            {"original": "Acme Corp", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
            {"original": "Beta LLC", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        dh = compute_dataset_hash_v1(records)
        assert len(dh) == 64

        # Step 2: tenant scope
        ts = compute_tenant_scope("tenant_shard", scope_key=TEST_SCOPE_KEY)
        assert len(ts) == 16

        # Step 3: deterministic receipt_id
        rid = deterministic_receipt_id(batch_id, root_hash)

        # Step 4: build manifest
        m = build_attestation_manifest_v1(
            batch_id=batch_id,
            root_hash=root_hash,
            artifact_mode="PRODUCTION_REAL",
            engine_version="8.2.2",
            environment="prod",
            config_hash="d" * 64,
            dataset_hash=dh,
            registry_hash="f" * 64,
            key_id="projects/p/locations/l/keyRings/kr/cryptoKeys/k/cryptoKeyVersions/1",
            metrics=VALID_METRICS,
            tenant_scope=ts,
            anchor_ref=VALID_ANCHOR_REF,
            artifact_hashes=[],
            receipt_id=rid,
        )
        assert m["protocol_version"] == "ia-attestation/v1"
        assert m["receipt_id"] == rid

        # Step 5: JCS canonical
        canonical = jcs_canonicalize(m)
        mhash = hashlib.sha256(canonical).hexdigest()

        # Step 6: pointer
        ptr = build_firestore_receipt_pointer(rid, f"gs://bucket/receipts/{ts}/{rid}")
        assert ptr["id"] == rid
        assert ptr["version"] == "ia-attestation/v1"
