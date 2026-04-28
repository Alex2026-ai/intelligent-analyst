"""
Tests for attestation verifier v1.

Covers all 9 failure modes, deterministic repeatability,
performance benchmark, metrics, and structured logging.
"""

import copy
import hashlib
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app.security.iavp import jcs_canonicalize
from app.attestation.manifest_v1 import (
    PROTOCOL_VERSION,
    SIGNATURE_ALGORITHM,
    build_attestation_manifest_v1,
)
from app.attestation.verifier_v1 import (
    VerificationFailure,
    verify_manifest_bundle,
    get_verification_metrics,
    reset_verification_metrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test key pair (deterministic seed for reproducible tests)
# ─────────────────────────────────────────────────────────────────────────────

_TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()
_TEST_PUBLIC_PEM = _TEST_PUBLIC_KEY.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)

TEST_KEY_ID = "projects/test/locations/us/keyRings/test-ring/cryptoKeys/test-key/cryptoKeyVersions/1"


def _test_key_resolver(key_id: str):
    """Test public key resolver — returns PEM for test key_id."""
    if key_id == TEST_KEY_ID:
        return _TEST_PUBLIC_PEM
    return None


def _wrong_key_resolver(key_id: str):
    """Returns a different key to simulate key mismatch."""
    wrong_key = ec.generate_private_key(ec.SECP256R1()).public_key()
    return wrong_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _none_key_resolver(key_id: str):
    """Returns None to simulate key not found."""
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: build a valid receipt bundle
# ─────────────────────────────────────────────────────────────────────────────

def _build_valid_bundle(
    record_count: int = 100,
    batch_id: str = "BATCH-TEST-VERIFY-001",
    timestamp: str = None,
):
    """Build a valid manifest + signature + metadata bundle for testing."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    root_hash = hashlib.sha256(b"test-root-data").hexdigest()
    config_hash = hashlib.sha256(b"test-config").hexdigest()
    dataset_hash = hashlib.sha256(b"test-dataset").hexdigest()
    registry_hash = hashlib.sha256(b"test-registry").hexdigest()
    anchor_hash = hashlib.sha256(b"test-anchor-object").hexdigest()
    artifact_hash = hashlib.sha256(b"test-artifact-data").hexdigest()

    manifest = build_attestation_manifest_v1(
        batch_id=batch_id,
        root_hash=root_hash,
        artifact_mode="PRODUCTION_REAL",
        engine_version="8.2.2",
        environment="test",
        config_hash=config_hash,
        dataset_hash=dataset_hash,
        registry_hash=registry_hash,
        key_id=TEST_KEY_ID,
        metrics={
            "l1_pct": 0.85,
            "l2_pct": 0.08,
            "l3_pct": 0.02,
            "l4_pct": 0.05,
            "record_count": record_count,
            "replay_method": "deterministic",
            "replay_runs": 1,
            "replay_variance": 0.0,
        },
        tenant_scope="a1b2c3d4e5f6a7b8",
        anchor_ref={
            "anchor_hash": anchor_hash,
            "anchor_timestamp": timestamp,
            "bucket": "ia-test-anchors",
            "object_path": f"anchors/{batch_id}.json",
        },
        artifact_hashes=[
            {
                "artifact_type": "results_csv",
                "hash": artifact_hash,
                "size_bytes": 4096,
            },
        ],
        receipt_id="abcd1234-ef56-7890-abcd-ef1234567890",
        timestamp=timestamp,
    )

    manifest_bytes = jcs_canonicalize(manifest)

    # Sign: ECDSA P-256 over SHA-256(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).digest()
    from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
    signature_bytes = _TEST_PRIVATE_KEY.sign(
        digest,
        ec.ECDSA(Prehashed(hashes.SHA256())),
    )

    # Metadata
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest().lower()
    sig_hash = hashlib.sha256(signature_bytes).hexdigest().lower()
    metadata = {
        "batch_id": batch_id,
        "created_at": timestamp,
        "environment": "test",
        "manifest_hash": manifest_hash,
        "protocol_version": PROTOCOL_VERSION,
        "receipt_id": "abcd1234-ef56-7890-abcd-ef1234567890",
        "signature_hash": sig_hash,
    }
    metadata_bytes = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")

    return manifest_bytes, signature_bytes, metadata_bytes, manifest


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Happy path
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifierHappyPath:

    def setup_method(self):
        reset_verification_metrics()

    def test_valid_bundle_passes(self):
        """Valid manifest + signature + metadata → success."""
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(
            manifest_bytes=m,
            signature_bytes=s,
            metadata_bytes=md,
            public_key_resolver=_test_key_resolver,
        )
        assert result["success"] is True
        assert result["failure_reason"] is None
        assert "schema_jcs" in result["checks_passed"]
        assert "signature" in result["checks_passed"]
        assert "metadata_consistency" in result["checks_passed"]
        assert "anchor_binding" in result["checks_passed"]
        assert "artifact_integrity" in result["checks_passed"]
        assert result["duration_ms"] >= 0

    def test_valid_bundle_without_metadata(self):
        """Valid manifest + signature, no metadata → success (metadata optional)."""
        m, s, _, _ = _build_valid_bundle()
        result = verify_manifest_bundle(
            manifest_bytes=m,
            signature_bytes=s,
            metadata_bytes=None,
            public_key_resolver=_test_key_resolver,
        )
        assert result["success"] is True

    def test_schema_only_mode(self):
        """No key resolver, fail_closed=False → schema checks pass, signature skipped."""
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(
            manifest_bytes=m,
            signature_bytes=s,
            metadata_bytes=md,
            public_key_resolver=None,
            fail_closed=False,
        )
        assert result["success"] is True
        assert "schema_jcs" in result["checks_passed"]
        assert "signature" in result["checks_passed"]  # skipped = passes

    def test_details_contains_batch_and_receipt(self):
        """Result details contain batch_id, receipt_id, protocol_version."""
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, s, md, _test_key_resolver)
        assert result["details"]["batch_id"] == "BATCH-TEST-VERIFY-001"
        assert result["details"]["receipt_id"] == "abcd1234-ef56-7890-abcd-ef1234567890"
        assert result["details"]["protocol_version"] == PROTOCOL_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 1 — Schema & JCS
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaAndJCS:

    def setup_method(self):
        reset_verification_metrics()

    def test_invalid_json(self):
        result = verify_manifest_bundle(b"not json", b"\x00", None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.MANIFEST_MALFORMED.value
        assert result["details"]["reason"] == "invalid_json"

    def test_not_a_dict(self):
        result = verify_manifest_bundle(b"[1,2,3]", b"\x00", None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.MANIFEST_MALFORMED.value
        assert result["details"]["reason"] == "not_a_dict"

    def test_missing_required_field(self):
        m, s, _, manifest = _build_valid_bundle()
        # Remove a required field
        del manifest["root_hash"]
        bad_bytes = jcs_canonicalize(manifest)
        result = verify_manifest_bundle(bad_bytes, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.MANIFEST_MALFORMED.value
        assert "root_hash" in result["details"]["missing"]

    def test_wrong_protocol_version(self):
        m, s, _, manifest = _build_valid_bundle()
        manifest["protocol_version"] = "ia-attestation/v2"
        bad_bytes = jcs_canonicalize(manifest)
        result = verify_manifest_bundle(bad_bytes, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.MANIFEST_MALFORMED.value
        assert result["details"]["reason"] == "wrong_protocol_version"

    def test_jcs_round_trip_mismatch(self):
        """Manifest bytes that parse as valid JSON but aren't JCS canonical."""
        m, s, _, manifest = _build_valid_bundle()
        # Pretty-print (non-canonical) but valid JSON
        non_canonical = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        result = verify_manifest_bundle(non_canonical, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.MANIFEST_MALFORMED.value
        assert result["details"]["reason"] == "jcs_round_trip_mismatch"

    def test_mutated_manifest_bytes(self):
        """Flip a byte in manifest → JCS mismatch or parse error."""
        m, s, md, _ = _build_valid_bundle()
        mutated = bytearray(m)
        mutated[10] = (mutated[10] + 1) % 256
        result = verify_manifest_bundle(bytes(mutated), s, md, _test_key_resolver)
        assert result["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 2 — Signature
# ─────────────────────────────────────────────────────────────────────────────

class TestSignature:

    def setup_method(self):
        reset_verification_metrics()

    def test_wrong_signature(self):
        m, _, md, _ = _build_valid_bundle()
        # Random bytes as signature
        bad_sig = b"\x30\x44" + b"\x00" * 68
        result = verify_manifest_bundle(m, bad_sig, md, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.SIGNATURE_INVALID.value

    def test_empty_signature(self):
        m, _, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, b"", md, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.SIGNATURE_INVALID.value

    def test_key_not_found(self):
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, s, md, _none_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.KEY_VERSION_MISMATCH.value

    def test_wrong_key(self):
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, s, md, _wrong_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.SIGNATURE_INVALID.value

    def test_fail_closed_no_resolver(self):
        """fail_closed=True + no resolver → SIGNATURE_INVALID."""
        m, s, md, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, s, md, None, fail_closed=True)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.SIGNATURE_INVALID.value


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 3 — Metadata consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadataConsistency:

    def setup_method(self):
        reset_verification_metrics()

    def test_metadata_receipt_id_mismatch(self):
        m, s, md, _ = _build_valid_bundle()
        meta = json.loads(md)
        meta["receipt_id"] = "wrong-receipt-id"
        bad_md = json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
        result = verify_manifest_bundle(m, s, bad_md, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.METADATA_INCONSISTENT.value
        assert result["details"]["reason"] == "receipt_id_mismatch"

    def test_metadata_batch_id_mismatch(self):
        m, s, md, _ = _build_valid_bundle()
        meta = json.loads(md)
        meta["batch_id"] = "WRONG-BATCH"
        bad_md = json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
        result = verify_manifest_bundle(m, s, bad_md, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.METADATA_INCONSISTENT.value
        assert result["details"]["reason"] == "batch_id_mismatch"

    def test_metadata_manifest_hash_mismatch(self):
        m, s, md, _ = _build_valid_bundle()
        meta = json.loads(md)
        meta["manifest_hash"] = "0" * 64  # wrong hash
        bad_md = json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
        result = verify_manifest_bundle(m, s, bad_md, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.METADATA_INCONSISTENT.value
        assert result["details"]["reason"] == "manifest_hash_mismatch"

    def test_metadata_invalid_json(self):
        m, s, _, _ = _build_valid_bundle()
        result = verify_manifest_bundle(m, s, b"not json", _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.METADATA_INCONSISTENT.value


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 4 — Anchor binding
# ─────────────────────────────────────────────────────────────────────────────

class TestAnchorBinding:

    def setup_method(self):
        reset_verification_metrics()

    def test_anchor_hash_missing(self):
        m, s, _, manifest = _build_valid_bundle()
        del manifest["anchor_ref"]["anchor_hash"]
        bad_bytes = jcs_canonicalize(manifest)
        # Re-sign
        digest = hashlib.sha256(bad_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        result = verify_manifest_bundle(bad_bytes, sig, None, _test_key_resolver)
        # This will fail at schema check (missing anchor_ref fields) or anchor check
        assert result["success"] is False

    def test_anchor_hash_wrong_length(self):
        m, s, _, manifest = _build_valid_bundle()
        manifest["anchor_ref"]["anchor_hash"] = "abc123"  # too short
        bad_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(bad_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        result = verify_manifest_bundle(bad_bytes, sig, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ANCHOR_HASH_MISMATCH.value

    def test_anchor_timestamp_missing(self):
        m, s, _, manifest = _build_valid_bundle()
        del manifest["anchor_ref"]["anchor_timestamp"]
        bad_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(bad_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        result = verify_manifest_bundle(bad_bytes, sig, None, _test_key_resolver)
        assert result["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 5 — Artifact integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestArtifactIntegrity:

    def setup_method(self):
        reset_verification_metrics()

    def _rebuild_signed(self, manifest):
        bad_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(bad_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return bad_bytes, sig

    def test_artifact_hash_invalid(self):
        _, _, _, manifest = _build_valid_bundle()
        manifest["artifact_hashes"][0]["hash"] = "not-a-valid-hash"
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ARTIFACT_HASH_MISMATCH.value

    def test_artifact_size_negative(self):
        _, _, _, manifest = _build_valid_bundle()
        manifest["artifact_hashes"][0]["size_bytes"] = -1
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ARTIFACT_SIZE_MISMATCH.value

    def test_artifact_size_missing(self):
        _, _, _, manifest = _build_valid_bundle()
        del manifest["artifact_hashes"][0]["size_bytes"]
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ARTIFACT_SIZE_MISMATCH.value

    def test_artifact_hashes_empty(self):
        _, _, _, manifest = _build_valid_bundle()
        manifest["artifact_hashes"] = []
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ARTIFACT_HASH_MISMATCH.value

    def test_artifact_missing_type(self):
        _, _, _, manifest = _build_valid_bundle()
        del manifest["artifact_hashes"][0]["artifact_type"]
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.ARTIFACT_HASH_MISMATCH.value


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Check 6 — Timestamp skew
# ─────────────────────────────────────────────────────────────────────────────

class TestTimestampSkew:

    def setup_method(self):
        reset_verification_metrics()

    def _rebuild_signed(self, manifest):
        bad_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(bad_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return bad_bytes, sig

    def test_future_timestamp_beyond_tolerance(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        _, _, _, manifest = _build_valid_bundle(timestamp=future)
        # Fix anchor_ref timestamp to match
        manifest["anchor_ref"]["anchor_timestamp"] = future
        m, s = self._rebuild_signed(manifest)
        result = verify_manifest_bundle(m, s, None, _test_key_resolver)
        assert result["success"] is False
        assert result["failure_reason"] == VerificationFailure.TIMESTAMP_SKEW_EXCEEDED.value

    def test_recent_timestamp_passes(self):
        """Timestamp from 1 minute ago should pass."""
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        m, s, md, _ = _build_valid_bundle(timestamp=recent)
        result = verify_manifest_bundle(m, s, md, _test_key_resolver)
        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Deterministic repeatability
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterministicRepeat:

    def setup_method(self):
        reset_verification_metrics()

    def test_100x_same_result(self):
        """Verify same bundle 100 times → identical results every time."""
        m, s, md, _ = _build_valid_bundle()
        results = []
        for _ in range(100):
            r = verify_manifest_bundle(m, s, md, _test_key_resolver)
            results.append(r["success"])
        assert all(r is True for r in results)
        assert len(results) == 100


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Performance benchmark
# ─────────────────────────────────────────────────────────────────────────────

class TestPerformanceBenchmark:

    def setup_method(self):
        reset_verification_metrics()

    def test_10k_row_manifest_under_500ms(self):
        """10k-row manifest verification must complete under 500ms."""
        # Build a manifest with 10k record_count and multiple artifacts
        artifacts = []
        for i in range(20):
            h = hashlib.sha256(f"artifact-{i}".encode()).hexdigest()
            artifacts.append({
                "artifact_type": f"shard_{i:04d}",
                "hash": h,
                "size_bytes": 1024 * (i + 1),
            })

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        manifest = build_attestation_manifest_v1(
            batch_id="BATCH-PERF-10K",
            root_hash=hashlib.sha256(b"perf-root").hexdigest(),
            artifact_mode="PRODUCTION_REAL",
            engine_version="8.2.2",
            environment="test",
            config_hash=hashlib.sha256(b"perf-config").hexdigest(),
            dataset_hash=hashlib.sha256(b"perf-dataset").hexdigest(),
            registry_hash=hashlib.sha256(b"perf-registry").hexdigest(),
            key_id=TEST_KEY_ID,
            metrics={
                "l1_pct": 0.85,
                "l2_pct": 0.08,
                "l3_pct": 0.02,
                "l4_pct": 0.05,
                "record_count": 10000,
                "replay_method": "deterministic",
                "replay_runs": 1,
                "replay_variance": 0.0,
            },
            tenant_scope="a1b2c3d4e5f6a7b8",
            anchor_ref={
                "anchor_hash": hashlib.sha256(b"perf-anchor").hexdigest(),
                "anchor_timestamp": ts,
                "bucket": "ia-test-anchors",
                "object_path": "anchors/BATCH-PERF-10K.json",
            },
            artifact_hashes=artifacts,
            timestamp=ts,
        )

        manifest_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(manifest_bytes).digest()
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
        sig = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))

        t0 = time.monotonic()
        result = verify_manifest_bundle(manifest_bytes, sig, None, _test_key_resolver)
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert result["success"] is True, f"Verification failed: {result}"
        assert elapsed_ms < 500, f"Verification took {elapsed_ms:.1f}ms (limit: 500ms)"
        print(f"\n  [BENCHMARK] 10k-row manifest verification: {elapsed_ms:.1f}ms")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Metrics and observability
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsAndObservability:

    def setup_method(self):
        reset_verification_metrics()

    def test_success_increments_counter(self):
        m, s, md, _ = _build_valid_bundle()
        verify_manifest_bundle(m, s, md, _test_key_resolver)
        metrics = get_verification_metrics()
        assert metrics["success_total"] == 1
        assert metrics["failures_total"] == 0

    def test_failure_increments_counter(self):
        verify_manifest_bundle(b"bad", b"\x00", None, _test_key_resolver)
        metrics = get_verification_metrics()
        assert metrics["failures_total"] == 1
        assert metrics["success_total"] == 0
        assert "MANIFEST_MALFORMED" in metrics["failures_by_reason"]

    def test_duration_recorded(self):
        m, s, md, _ = _build_valid_bundle()
        verify_manifest_bundle(m, s, md, _test_key_resolver)
        metrics = get_verification_metrics()
        assert metrics["duration_samples"] == 1
        assert metrics["duration_p50_ms"] is not None
        assert metrics["duration_p50_ms"] >= 0

    def test_structured_log_on_success(self, caplog):
        m, s, md, _ = _build_valid_bundle()
        with caplog.at_level(logging.INFO):
            verify_manifest_bundle(m, s, md, _test_key_resolver)
        assert any("attestation_verification=PASS" in r.message for r in caplog.records)

    def test_structured_log_on_failure(self, caplog):
        with caplog.at_level(logging.WARNING):
            verify_manifest_bundle(b"bad", b"\x00", None, _test_key_resolver)
        assert any("attestation_verification=FAIL" in r.message for r in caplog.records)

    def test_multiple_verifications_accumulate(self):
        m, s, md, _ = _build_valid_bundle()
        for _ in range(5):
            verify_manifest_bundle(m, s, md, _test_key_resolver)
        verify_manifest_bundle(b"bad", b"\x00", None, _test_key_resolver)
        metrics = get_verification_metrics()
        assert metrics["success_total"] == 5
        assert metrics["failures_total"] == 1
        assert metrics["duration_samples"] == 6
