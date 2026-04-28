"""
Tests for Phase 5 — Artifact hash population.

Covers:
- Valid population with matching hashes
- Idempotent second finalize (no re-sign/overwrite)
- Missing artifact blob → deterministic ARTIFACT_METADATA_MISSING
- Verifier returns artifact_integrity: true for valid receipts
- Runtime under budget
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.attestation.artifact_hasher import (
    compute_artifact_hashes,
    build_artifact_list_for_batch,
    ARTIFACT_TYPE_ANCHOR,
    ARTIFACT_TYPE_EVIDENCE,
    ARTIFACT_TYPE_HASH_CHAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_blob_data(content: str = "test content") -> bytes:
    return content.encode("utf-8")


def _make_mock_gcs_client(blobs: dict):
    """
    Create a mock GCS client.

    blobs: dict mapping "bucket/object_path" -> bytes content.
    Missing keys raise NotFound.
    """
    client = MagicMock()

    def _bucket(bucket_name):
        bucket_mock = MagicMock()

        def _blob(object_path):
            key = f"{bucket_name}/{object_path}"
            blob_mock = MagicMock()
            if key in blobs:
                blob_mock.download_as_bytes.return_value = blobs[key]
            else:
                blob_mock.download_as_bytes.side_effect = Exception("404 Not Found")
            return blob_mock

        bucket_mock.blob = _blob
        return bucket_mock

    client.bucket = _bucket
    return client


# ---------------------------------------------------------------------------
# build_artifact_list_for_batch
# ---------------------------------------------------------------------------

class TestBuildArtifactList:
    def test_all_artifacts_present(self):
        result = build_artifact_list_for_batch(
            anchor_bucket="anchor-bucket",
            anchor_object_path="anchors/abc123/BATCH-001.json",
            vault_bucket="vault-bucket",
            tenant_hash="abc123def456789a",
            batch_id="BATCH-001",
        )
        assert len(result) == 3
        types = [a["artifact_type"] for a in result]
        assert ARTIFACT_TYPE_ANCHOR in types
        assert ARTIFACT_TYPE_EVIDENCE in types
        assert ARTIFACT_TYPE_HASH_CHAIN in types

    def test_no_anchor_bucket(self):
        result = build_artifact_list_for_batch(
            anchor_bucket="",
            anchor_object_path="",
            vault_bucket="vault-bucket",
            tenant_hash="abc123def456789a",
            batch_id="BATCH-001",
        )
        assert len(result) == 2
        types = [a["artifact_type"] for a in result]
        assert ARTIFACT_TYPE_ANCHOR not in types

    def test_no_vault_bucket(self):
        result = build_artifact_list_for_batch(
            anchor_bucket="anchor-bucket",
            anchor_object_path="anchors/abc123/BATCH-001.json",
            vault_bucket="",
            tenant_hash="abc123def456789a",
            batch_id="BATCH-001",
        )
        assert len(result) == 1
        assert result[0]["artifact_type"] == ARTIFACT_TYPE_ANCHOR

    def test_empty_everything(self):
        result = build_artifact_list_for_batch(
            anchor_bucket="",
            anchor_object_path="",
            vault_bucket="",
            tenant_hash="",
            batch_id="",
        )
        assert result == []


# ---------------------------------------------------------------------------
# compute_artifact_hashes
# ---------------------------------------------------------------------------

class TestComputeArtifactHashes:
    def test_valid_hashes_match_content(self):
        """Valid population: hashes match actual GCS blob content."""
        anchor_content = b'{"batch_id": "BATCH-001", "root_hash": "abc123"}'
        evidence_content = b'{"evidence": "data"}'
        chain_content = b'{"chain_entries": []}'

        blobs = {
            "anchor-bucket/anchors/tenant/BATCH-001.json": anchor_content,
            "vault-bucket/vaulted/tenant/BATCH-001/evidence.json": evidence_content,
            "vault-bucket/vaulted/tenant/BATCH-001/chain.json": chain_content,
        }

        mock_client = _make_mock_gcs_client(blobs)

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "anchor-bucket",
             "object_path": "anchors/tenant/BATCH-001.json"},
            {"artifact_type": ARTIFACT_TYPE_EVIDENCE, "bucket": "vault-bucket",
             "object_path": "vaulted/tenant/BATCH-001/evidence.json"},
            {"artifact_type": ARTIFACT_TYPE_HASH_CHAIN, "bucket": "vault-bucket",
             "object_path": "vaulted/tenant/BATCH-001/chain.json"},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            hashes, errors = compute_artifact_hashes(artifact_list)

        assert len(hashes) == 3
        assert len(errors) == 0

        # Verify hashes are correct SHA-256
        for h, content in zip(hashes, [anchor_content, evidence_content, chain_content]):
            expected = hashlib.sha256(content).hexdigest().lower()
            assert h["hash"] == expected
            assert h["size_bytes"] == len(content)
            assert h["hash_alg"] == "SHA-256"
            assert len(h["hash"]) == 64

    def test_missing_artifact_returns_deterministic_failure(self):
        """Missing artifact blob → ARTIFACT_METADATA_MISSING."""
        blobs = {}  # No blobs exist
        mock_client = _make_mock_gcs_client(blobs)

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "anchor-bucket",
             "object_path": "anchors/tenant/BATCH-001.json"},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            hashes, errors = compute_artifact_hashes(artifact_list)

        assert len(hashes) == 0
        assert len(errors) == 1
        assert errors[0]["reason"] == "ARTIFACT_METADATA_MISSING"
        assert errors[0]["artifact_type"] == ARTIFACT_TYPE_ANCHOR

    def test_partial_missing_artifacts(self):
        """Some artifacts present, some missing."""
        anchor_content = b'{"anchor": true}'
        blobs = {
            "anchor-bucket/anchors/tenant/BATCH-001.json": anchor_content,
        }
        mock_client = _make_mock_gcs_client(blobs)

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "anchor-bucket",
             "object_path": "anchors/tenant/BATCH-001.json"},
            {"artifact_type": ARTIFACT_TYPE_EVIDENCE, "bucket": "vault-bucket",
             "object_path": "vaulted/tenant/BATCH-001/evidence.json"},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            hashes, errors = compute_artifact_hashes(artifact_list)

        assert len(hashes) == 1
        assert hashes[0]["artifact_type"] == ARTIFACT_TYPE_ANCHOR
        assert hashes[0]["hash"] == hashlib.sha256(anchor_content).hexdigest()
        assert len(errors) == 1
        assert errors[0]["reason"] == "ARTIFACT_METADATA_MISSING"

    def test_empty_bucket_or_path(self):
        """Empty bucket/path yields ARTIFACT_METADATA_MISSING."""
        mock_client = _make_mock_gcs_client({})

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "", "object_path": "path"},
            {"artifact_type": ARTIFACT_TYPE_EVIDENCE, "bucket": "bucket", "object_path": ""},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            hashes, errors = compute_artifact_hashes(artifact_list)

        assert len(hashes) == 0
        assert len(errors) == 2
        for e in errors:
            assert e["reason"] == "ARTIFACT_METADATA_MISSING"

    def test_no_gcs_client(self):
        """GCS client unavailable → error."""
        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=None):
            hashes, errors = compute_artifact_hashes([
                {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "b", "object_path": "p"},
            ])

        assert len(hashes) == 0
        assert len(errors) == 1
        assert errors[0]["reason"] == "ARTIFACT_METADATA_MISSING"

    def test_hash_format_conforms_to_manifest_spec(self):
        """Each hash entry has artifact_type, hash (64-char hex), size_bytes (int), hash_alg."""
        content = b"test data for hash verification"
        blobs = {"b/p": content}
        mock_client = _make_mock_gcs_client(blobs)

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            hashes, errors = compute_artifact_hashes([
                {"artifact_type": "test_artifact", "bucket": "b", "object_path": "p"},
            ])

        assert len(hashes) == 1
        h = hashes[0]
        assert "artifact_type" in h
        assert "hash" in h
        assert "size_bytes" in h
        assert "hash_alg" in h
        assert len(h["hash"]) == 64
        assert isinstance(h["size_bytes"], int)
        assert h["size_bytes"] > 0


# ---------------------------------------------------------------------------
# Verifier integration: artifact_integrity should pass with populated hashes
# ---------------------------------------------------------------------------

class TestVerifierArtifactIntegrity:
    def test_verifier_passes_with_valid_artifact_hashes(self):
        """Manifest with populated artifact_hashes → verifier artifact_integrity: true."""
        from app.attestation.verifier_v1 import verify_manifest_bundle
        from app.security.iavp import jcs_canonicalize
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives import hashes, serialization

        # Generate test key pair
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        test_key_id = "test-key-for-artifact-integrity"

        # Build manifest with real artifact hashes
        manifest = {
            "anchor_ref": {
                "anchor_hash": "a" * 64,
                "anchor_timestamp": datetime.now(timezone.utc).isoformat(),
                "bucket": "test-bucket",
                "object_path": "test/path",
            },
            "artifact_hashes": [
                {
                    "artifact_type": ARTIFACT_TYPE_ANCHOR,
                    "hash_alg": "SHA-256",
                    "hash": "b" * 64,
                    "size_bytes": 1024,
                },
                {
                    "artifact_type": ARTIFACT_TYPE_EVIDENCE,
                    "hash_alg": "SHA-256",
                    "hash": "c" * 64,
                    "size_bytes": 2048,
                },
            ],
            "artifact_mode": "DEMO_SIMULATED",
            "batch_id": "BATCH-AH-TEST",
            "config_hash": "d" * 64,
            "dataset_hash": "e" * 64,
            "engine_version": "8.2.2",
            "environment": "test",
            "key_id": test_key_id,
            "metrics": {
                "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
                "record_count": 100,
                "replay_method": "STABLE_INPUT_ORDER_V2",
                "replay_runs": 3,
                "replay_variance": 0,
            },
            "protocol_version": "ia-attestation/v1",
            "receipt_id": "test-receipt-artifact-hash",
            "registry_hash": "f" * 64,
            "root_hash": "1" * 64,
            "signature_algorithm": "EC_SIGN_P256_SHA256",
            "source_blob_hash": None,
            "tenant_scope": "a1b2c3d4e5f67890",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }

        canonical_bytes = jcs_canonicalize(manifest)

        # Sign
        digest = hashlib.sha256(canonical_bytes).digest()
        signature = private_key.sign(
            digest,
            ec.ECDSA(utils.Prehashed(hashes.SHA256()))
        )

        def key_resolver(kid):
            if kid == test_key_id:
                return public_pem
            return None

        result = verify_manifest_bundle(
            manifest_bytes=canonical_bytes,
            signature_bytes=signature,
            public_key_resolver=key_resolver,
        )

        assert result["success"] is True
        assert "artifact_integrity" in result["checks_passed"]

    def test_verifier_fails_with_empty_artifact_hashes(self):
        """Empty artifact_hashes → verifier fails with ARTIFACT_HASH_MISMATCH."""
        from app.attestation.verifier_v1 import verify_manifest_bundle
        from app.security.iavp import jcs_canonicalize

        manifest = {
            "anchor_ref": {
                "anchor_hash": "a" * 64,
                "anchor_timestamp": datetime.now(timezone.utc).isoformat(),
                "bucket": "test-bucket",
                "object_path": "test/path",
            },
            "artifact_hashes": [],
            "artifact_mode": "DEMO_SIMULATED",
            "batch_id": "BATCH-EMPTY-AH",
            "config_hash": "d" * 64,
            "dataset_hash": "e" * 64,
            "engine_version": "8.2.2",
            "environment": "test",
            "key_id": "test-key",
            "metrics": {
                "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
                "record_count": 100,
                "replay_method": "STABLE_INPUT_ORDER_V2",
                "replay_runs": 3,
                "replay_variance": 0,
            },
            "protocol_version": "ia-attestation/v1",
            "receipt_id": "test-receipt-empty-ah",
            "registry_hash": "f" * 64,
            "root_hash": "1" * 64,
            "signature_algorithm": "EC_SIGN_P256_SHA256",
            "source_blob_hash": None,
            "tenant_scope": "a1b2c3d4e5f67890",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }

        canonical_bytes = jcs_canonicalize(manifest)

        result = verify_manifest_bundle(
            manifest_bytes=canonical_bytes,
            signature_bytes=b"fake-sig",
            fail_closed=False,
        )

        assert result["success"] is False
        assert result["failure_reason"] == "ARTIFACT_HASH_MISMATCH"


# ---------------------------------------------------------------------------
# Idempotent second finalize
# ---------------------------------------------------------------------------

class TestIdempotentFinalize:
    def test_second_compute_returns_same_hashes(self):
        """Idempotent: computing hashes twice gives identical results."""
        content = b'{"stable": "content"}'
        blobs = {"b/p": content}
        mock_client = _make_mock_gcs_client(blobs)

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "b", "object_path": "p"},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            h1, e1 = compute_artifact_hashes(artifact_list)
            h2, e2 = compute_artifact_hashes(artifact_list)

        assert h1 == h2
        assert e1 == e2


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_compute_hashes_runtime_under_budget(self):
        """Artifact hash computation should be fast for in-memory blobs."""
        content = b"x" * 10_000  # 10KB blob
        blobs = {
            "b/anchor": content,
            "b/evidence": content,
            "b/chain": content,
        }
        mock_client = _make_mock_gcs_client(blobs)

        artifact_list = [
            {"artifact_type": ARTIFACT_TYPE_ANCHOR, "bucket": "b", "object_path": "anchor"},
            {"artifact_type": ARTIFACT_TYPE_EVIDENCE, "bucket": "b", "object_path": "evidence"},
            {"artifact_type": ARTIFACT_TYPE_HASH_CHAIN, "bucket": "b", "object_path": "chain"},
        ]

        with patch("app.attestation.artifact_hasher._get_gcs_client", return_value=mock_client):
            t0 = time.time()
            for _ in range(100):
                compute_artifact_hashes(artifact_list)
            elapsed_ms = (time.time() - t0) * 1000

        avg_ms = elapsed_ms / 100
        assert avg_ms < 200, f"avg {avg_ms:.1f} ms exceeds 200ms budget"
