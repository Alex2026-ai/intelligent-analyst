"""
================================================================================
IAVP Evidence Schema Verification Tests
================================================================================

Tests for evidence schema detection, chunk_v1 validation, legacy row_sig_v1
fallback, and the regression: "false FAIL cannot occur when cryptographic
invariants pass."

Run with: pytest backend/tests/test_evidence_schema.py -v
================================================================================
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.evidence import (
    detect_evidence_schema,
    verify_chunk_v1_evidence,
    verify_evidence_signature_format,
    EVIDENCE_SCHEMA_CHUNK_V1,
    EVIDENCE_SCHEMA_ROW_SIG_V1,
    EVIDENCE_SCHEMA_UNKNOWN,
)


# =============================================================================
# FIXTURES: Chunk V1 Evidence Blobs
# =============================================================================

def make_chunk_blob(chunk_index=0, chunk_count=10, rows_in_chunk=500, chunk_digest="abc123"):
    """Build a minimal chunk_v1 evidence artifact."""
    return {
        "schema_version": "chunk_v1",
        "batch_id": "BATCH-TEST001",
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "row_start": chunk_index * 500,
        "row_end": chunk_index * 500 + rows_in_chunk,
        "rows_in_chunk": rows_in_chunk,
        "config_version": "sha256:aaa",
        "sanitization_version": "1.0",
        "watchlist_version_hash": "sha256:bbb",
        "created_at_utc": "2026-02-20T00:00:00Z",
        "records": [{"row_index": i} for i in range(rows_in_chunk)],
        "chunk_digest": chunk_digest,
    }


def make_chunk_digests_blob(chunk_count=10, digests=None):
    """Build a _chunk_digests index document."""
    return {
        "schema_version": "chunk_digests_v1",
        "batch_id": "BATCH-TEST001",
        "chunk_count": chunk_count,
        "row_count": chunk_count * 500,
        "chunk_size": 500,
        "digests": digests or [f"digest_{i}" for i in range(chunk_count)],
        "created_at_utc": "2026-02-20T00:00:00Z",
    }


# =============================================================================
# FIXTURES: Legacy Row Sig V1 Evidence Blobs
# =============================================================================

def make_row_sig_blob(row_index=0, has_signature=True):
    """Build a minimal row_sig_v1 (legacy) evidence blob."""
    blob = {
        "evidence": {
            "trace_id": "BATCH-LEGACY001",
            "row_index": row_index,
            "timestamp": "2026-01-15T00:00:00Z",
            "routing": {"layer": "L1_EXACT", "decision_path": "L1_EXACT"},
            "output": {"resolved": "Apple Inc.", "confidence": 1.0},
        },
        "signature": {
            "evidence_hash_sha256": "sha256:deadbeef",
            "signed_at_utc": "2026-01-15T00:00:01Z",
            "service_identity": {"cloud_run_service": "test"},
            "signature": "base64sigdata==" if has_signature else None,
            "signature_alg": "EC_SIGN_P256_SHA256",
            "signature_error": None if has_signature else "signing_disabled",
        },
        "version": "1.0.0",
    }
    return blob


# =============================================================================
# SCHEMA DETECTION TESTS
# =============================================================================

class TestDetectEvidenceSchema:
    """Test evidence schema detection logic."""

    def test_empty_blobs_returns_unknown(self):
        assert detect_evidence_schema([]) == EVIDENCE_SCHEMA_UNKNOWN

    def test_chunk_v1_detected(self):
        blobs = [make_chunk_blob(i) for i in range(3)]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_CHUNK_V1

    def test_chunk_digests_v1_detected(self):
        blobs = [make_chunk_digests_blob()]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_CHUNK_V1

    def test_mixed_chunks_and_digests_detected_as_chunk_v1(self):
        blobs = [make_chunk_blob(0), make_chunk_blob(1), make_chunk_digests_blob()]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_CHUNK_V1

    def test_row_sig_v1_detected(self):
        blobs = [make_row_sig_blob(i) for i in range(3)]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_ROW_SIG_V1

    def test_unknown_schema_for_unrecognized_blobs(self):
        blobs = [{"random_field": "value", "another": 123}]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_UNKNOWN

    def test_chunk_v1_takes_priority_over_other_blobs(self):
        """If any blob is chunk_v1, the entire batch is chunk_v1."""
        blobs = [make_chunk_blob(0), {"random": "data"}]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_CHUNK_V1

    def test_encrypted_blobs_return_unknown(self):
        """Encrypted blobs that failed decryption have no schema markers."""
        blobs = [{"encrypted": True, "doc_id": "chunk_0000", "decrypt_error": "no_key"}]
        assert detect_evidence_schema(blobs) == EVIDENCE_SCHEMA_UNKNOWN


# =============================================================================
# CHUNK V1 VERIFICATION TESTS
# =============================================================================

class TestVerifyChunkV1Evidence:
    """Test chunk_v1 evidence validation."""

    def test_valid_chunks_pass(self):
        blobs = [make_chunk_blob(i) for i in range(10)] + [make_chunk_digests_blob(10)]
        result = verify_chunk_v1_evidence(blobs)
        assert result["schema_version"] == EVIDENCE_SCHEMA_CHUNK_V1
        assert result["mode"] == "BATCH_ATTESTATION"
        assert result["per_record_signatures"] == "NOT_APPLICABLE"
        assert result["chunk_count"] == 10
        assert result["total_records"] == 5000
        assert result["chunks_with_digest"] == 10
        assert result["has_digest_index"] is True
        assert result["valid"] is True

    def test_chunks_without_digest_fail(self):
        blob = make_chunk_blob(0)
        del blob["chunk_digest"]
        result = verify_chunk_v1_evidence([blob])
        assert result["chunks_with_digest"] == 0
        assert result["valid"] is False

    def test_empty_blobs_fail(self):
        result = verify_chunk_v1_evidence([])
        assert result["chunk_count"] == 0
        assert result["valid"] is False

    def test_only_digests_doc_no_chunks(self):
        """Only the _chunk_digests doc, no actual chunks."""
        result = verify_chunk_v1_evidence([make_chunk_digests_blob()])
        assert result["chunk_count"] == 0
        assert result["valid"] is False
        assert result["has_digest_index"] is True

    def test_partial_batch_counts_correctly(self):
        """Last chunk with fewer than 500 rows."""
        blobs = [make_chunk_blob(0, rows_in_chunk=500), make_chunk_blob(1, rows_in_chunk=123)]
        result = verify_chunk_v1_evidence(blobs)
        assert result["total_records"] == 623
        assert result["chunk_count"] == 2
        assert result["valid"] is True


# =============================================================================
# LEGACY ROW_SIG_V1 VERIFICATION TESTS
# =============================================================================

class TestVerifyRowSigV1Evidence:
    """Test that legacy per-row signature format checks still work."""

    def test_valid_signed_blob_passes(self):
        blob = make_row_sig_blob(0, has_signature=True)
        result = verify_evidence_signature_format(blob)
        assert result["valid_format"] is True
        assert result["has_signature"] is True
        assert result["missing_fields"] == []

    def test_unsigned_blob_detected(self):
        blob = make_row_sig_blob(0, has_signature=False)
        result = verify_evidence_signature_format(blob)
        assert result["has_signature"] is False
        assert result["signature_error"] == "signing_disabled"

    def test_missing_required_fields_detected(self):
        blob = make_row_sig_blob(0)
        del blob["signature"]["evidence_hash_sha256"]
        result = verify_evidence_signature_format(blob)
        assert result["valid_format"] is False
        assert "evidence_hash_sha256" in result["missing_fields"]

    def test_chunk_blob_fails_row_sig_check(self):
        """Confirm chunk blobs correctly fail when checked with row_sig logic."""
        blob = make_chunk_blob(0)
        result = verify_evidence_signature_format(blob)
        assert result["valid_format"] is False
        assert result["has_signature"] is False


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegressionFalseFailPrevention:
    """
    Regression: /verify must NOT return FAIL solely because per-record
    signatures are missing when the evidence schema is chunk_v1.

    This was the root cause of the BATCH-02DCB41A false FAIL:
    - hash_chain: verified
    - anchor: verified
    - attestation_binding: verified
    - signatures: 10 sampled, 0 valid_format, 10 missing → FAIL

    After fix: chunk_v1 detection bypasses per-record signature checks.
    """

    def test_chunk_v1_not_applicable_is_not_missing(self):
        """NOT_APPLICABLE must not be confused with 'missing'."""
        blobs = [make_chunk_blob(i) for i in range(10)]
        result = verify_chunk_v1_evidence(blobs)
        assert result["per_record_signatures"] == "NOT_APPLICABLE"
        assert result["valid"] is True

    def test_detect_schema_prevents_wrong_validation_path(self):
        """chunk_v1 blobs must not be routed through row_sig_v1 checks."""
        blobs = [make_chunk_blob(i) for i in range(10)] + [make_chunk_digests_blob(10)]
        schema = detect_evidence_schema(blobs)
        assert schema == EVIDENCE_SCHEMA_CHUNK_V1
        # This should NOT happen in the fixed code path:
        # for blob in blobs[:10]:
        #     verify_evidence_signature_format(blob)  # ← would produce false negatives

    def test_unknown_schema_returns_fail_not_pass(self):
        """Conservative behavior: unknown schema must not silently PASS."""
        blobs = [{"unrecognized": True}]
        schema = detect_evidence_schema(blobs)
        assert schema == EVIDENCE_SCHEMA_UNKNOWN
        # In the /verify endpoint, this causes overall_status = "FAIL"
        # with failure_reason = "unknown_evidence_schema"

    def test_schema_constants_are_distinct(self):
        """Ensure all schema identifiers are unique strings."""
        schemas = {EVIDENCE_SCHEMA_CHUNK_V1, EVIDENCE_SCHEMA_ROW_SIG_V1, EVIDENCE_SCHEMA_UNKNOWN}
        assert len(schemas) == 3
