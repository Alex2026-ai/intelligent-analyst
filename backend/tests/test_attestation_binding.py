"""
FE-5.2 Regression Tests: Attestation Binding Upgrade

Verifies that ALL critical attestation fields are cryptographically bound
to the ECDSA signature. Modifying ANY field must FAIL verification.

Uses a locally-generated ECDSA P-256 key pair (no KMS dependency).
"""

import base64
import json
import pytest

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

from app.security.iavp import (
    jcs_canonicalize,
    jcs_sha256,
    build_attestation_payload,
    ATTESTATION_PAYLOAD_VERSION,
    IAVP_PROTOCOL_VERSION,
)
from app.security.public_verify import (
    verify_attestation_binding,
    _verify_ecdsa_signature,
    _verify_payload_matches_batch,
)

# ============================================================================
# TEST FIXTURES: Local ECDSA P-256 key pair (no KMS)
# ============================================================================

_private_key = ec.generate_private_key(ec.SECP256R1())
_public_key = _private_key.public_key()
TEST_PUBKEY_PEM = _public_key.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def mock_sign(data: bytes) -> str:
    """Sign bytes with the test private key, return base64."""
    sig = _private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode()


def _make_payload(**overrides):
    """Build a default attestation payload, with optional overrides."""
    defaults = {
        "batch_id": "BATCH-TEST1234",
        "root_hash": "a" * 64,
        "artifact_mode": "PRODUCTION_REAL",
        "engine_version": "3.0.0",
        "environment": "prod",
        "protocol_version": IAVP_PROTOCOL_VERSION,
        "config_hash": "b" * 64,
        "dataset_hash": "c" * 64,
        "key_id": "projects/test/locations/us/keyRings/test/cryptoKeys/test",
        "metrics_hash": "d" * 64,
        "record_count": 1000,
        "signed_at_utc": "2026-02-20T12:00:00.000000Z",
        "tenant_region": "us",
    }
    defaults.update(overrides)
    return build_attestation_payload(**defaults)


def _make_signed_batch(**payload_overrides):
    """Build a complete batch dict with valid attestation + matching data."""
    metrics = {"l1_pct": 80.0, "l2_pct": 10.0, "l3_pct": 5.0, "l4_pct": 5.0,
               "replay_runs": 3, "replay_variance": 0, "replay_method": "FULL_BATCH_REPROCESS"}

    # Use real metrics hash unless caller overrides it
    if "metrics_hash" not in payload_overrides:
        payload_overrides["metrics_hash"] = jcs_sha256(metrics)

    payload = _make_payload(**payload_overrides)
    canonical = jcs_canonicalize(payload)
    sig = mock_sign(canonical)

    return {
        "trace_id": payload["batch_id"],
        "attestation": {
            "signed_payload_jcs_b64": base64.b64encode(canonical).decode(),
            "signature_b64": sig,
            "algorithm": "ECDSA_P256_SHA256",
            "key_id": payload["key_id"],
            "key_version": "1",
            "attestation_version": ATTESTATION_PAYLOAD_VERSION,
            "error": None,
        },
        "signature": {
            "evidence_hash_sha256": payload["root_hash_sha256"],
            "signature": mock_sign(payload["root_hash_sha256"].encode()),
            "algorithm": "ECDSA_P256_SHA256",
        },
        "hash_chain": {
            "batch_root_hash": payload["root_hash_sha256"],
            "chain_length": payload["record_count"],
        },
        "iavp_manifest": {
            "artifact_mode": payload["artifact_mode"],
            "metrics": metrics,
        },
    }


# ============================================================================
# TEST 1: Attestation Payload Schema
# ============================================================================

class TestAttestationPayloadSchema:

    def test_payload_has_all_15_fields(self):
        payload = _make_payload()
        required = [
            "attestation_version", "artifact_mode", "batch_id",
            "config_hash_sha256", "dataset_hash_sha256", "engine_version",
            "environment", "key_id", "metrics_hash_sha256",
            "protocol_version", "record_count", "root_hash_sha256",
            "signed_at_utc", "tenant_id_hash_sha256", "tenant_region",
        ]
        for field in required:
            assert field in payload, f"Missing required field: {field}"
        assert len(payload) == 15

    def test_attestation_version(self):
        payload = _make_payload()
        assert payload["attestation_version"] == "1.2"

    def test_jcs_determinism(self):
        """Same payload must produce identical JCS bytes across runs."""
        payload = _make_payload()
        bytes1 = jcs_canonicalize(payload)
        bytes2 = jcs_canonicalize(payload)
        assert bytes1 == bytes2

    def test_jcs_output_is_valid_json(self):
        payload = _make_payload()
        canonical = jcs_canonicalize(payload)
        parsed = json.loads(canonical.decode('utf-8'))
        assert parsed["artifact_mode"] == "PRODUCTION_REAL"


# ============================================================================
# TEST 2: FE-5.2 Regression — Artifact Mode Tampering
# ============================================================================

class TestFE52Regression:

    def test_artifact_mode_tamper_in_manifest_fails_cross_check(self):
        """
        Attacker modifies iavp_manifest.artifact_mode in Firestore
        but leaves attestation blob unchanged → cross-check catches mismatch.
        """
        batch = _make_signed_batch()

        # Verify untampered first
        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is True
        assert mode == "ATTESTATION_BINDING_V1"

        # TAMPER: Change artifact_mode in manifest
        batch["iavp_manifest"]["artifact_mode"] = "DEMO_SIMULATED"

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is False
        assert "artifact_mode mismatch" in error
        assert mode == "ATTESTATION_BINDING_V1"

    def test_artifact_mode_tamper_in_payload_fails_crypto(self):
        """
        Attacker modifies signed_payload_jcs_b64 to change artifact_mode
        but keeps original signature → ECDSA verification fails.
        """
        batch = _make_signed_batch()
        original_sig = batch["attestation"]["signature_b64"]

        # Decode, tamper, re-encode the payload
        canonical = base64.b64decode(batch["attestation"]["signed_payload_jcs_b64"])
        tampered = json.loads(canonical.decode())
        tampered["artifact_mode"] = "DEMO_SIMULATED"
        tampered_canonical = jcs_canonicalize(tampered)

        # Also tamper the manifest to match (so cross-check won't catch it)
        batch["iavp_manifest"]["artifact_mode"] = "DEMO_SIMULATED"
        batch["attestation"]["signed_payload_jcs_b64"] = base64.b64encode(
            tampered_canonical
        ).decode()
        # Keep original signature (should now fail crypto)

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is False
        assert "Signature verification failed" in error


# ============================================================================
# TEST 3: Field Tampering Matrix — Every field must be bound
# ============================================================================

class TestFieldTamperingMatrix:

    @pytest.mark.parametrize("field,tampered_value", [
        ("artifact_mode", "DEMO_SIMULATED"),
        ("environment", "test"),
        ("config_hash_sha256", "0" * 64),
        ("root_hash_sha256", "deadbeef" * 8),
        ("engine_version", "0.0.1"),
        ("batch_id", "BATCH-EVIL"),
        ("record_count", 999999),
        ("dataset_hash_sha256", "0" * 64),
        ("metrics_hash_sha256", "0" * 64),
        ("key_id", "evil-key"),
        ("protocol_version", "IA-VP-0.0"),
        ("signed_at_utc", "2020-01-01T00:00:00.000000Z"),
    ])
    def test_single_field_tamper_fails(self, field, tampered_value):
        """Changing any single field in the payload must invalidate the signature."""
        batch = _make_signed_batch()

        # Decode payload, tamper one field, re-encode
        canonical = base64.b64decode(batch["attestation"]["signed_payload_jcs_b64"])
        payload = json.loads(canonical.decode())
        original_sig = batch["attestation"]["signature_b64"]

        payload[field] = tampered_value
        tampered_canonical = jcs_canonicalize(payload)
        batch["attestation"]["signed_payload_jcs_b64"] = base64.b64encode(
            tampered_canonical
        ).decode()

        # Also update batch fields to match tampered payload (so cross-check won't help)
        if field == "artifact_mode":
            batch["iavp_manifest"]["artifact_mode"] = tampered_value
        elif field == "root_hash_sha256":
            batch["hash_chain"]["batch_root_hash"] = tampered_value
        elif field == "batch_id":
            batch["trace_id"] = tampered_value

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is False, f"Tampering '{field}' should fail verification"
        assert "Signature verification failed" in error


# ============================================================================
# TEST 4: Backward Compatibility
# ============================================================================

class TestBackwardCompatibility:

    def test_legacy_batch_uses_root_hash_mode(self):
        """Batch without attestation field uses LEGACY_ROOT_HASH mode."""
        root_hash = "a" * 64
        batch = {
            "signature": {
                "evidence_hash_sha256": root_hash,
                "signature": mock_sign(root_hash.encode()),
            },
            # No "attestation" field
        }

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert mode == "LEGACY_ROOT_HASH"
        assert valid is True

    def test_new_batch_uses_attestation_mode(self):
        """Batch with attestation field uses ATTESTATION_BINDING_V1 mode."""
        batch = _make_signed_batch()

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert mode == "ATTESTATION_BINDING_V1"
        assert valid is True

    def test_batch_with_no_signature_at_all(self):
        """Batch with no signature returns LEGACY_ROOT_HASH with error."""
        batch = {"signature": {}}

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert mode == "LEGACY_ROOT_HASH"
        assert valid is False


# ============================================================================
# TEST 5: Metrics Hash Binding
# ============================================================================

class TestMetricsHashBinding:

    def test_metrics_tamper_detected_via_cross_check(self):
        """Tampering metrics in manifest is detected by metrics_hash mismatch."""
        batch = _make_signed_batch()

        # Verify the metrics_hash was computed from the manifest metrics
        manifest_metrics = batch["iavp_manifest"]["metrics"]

        # TAMPER: Change l1_pct in manifest metrics
        batch["iavp_manifest"]["metrics"]["l1_pct"] = 99.99

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is False
        assert "metrics_hash mismatch" in error

    def test_untampered_metrics_pass(self):
        """Correct metrics hash passes cross-check."""
        # Build batch where metrics_hash actually matches manifest metrics
        metrics = {"l1_pct": 80.0, "l2_pct": 10.0, "l3_pct": 5.0, "l4_pct": 5.0,
                   "replay_runs": 3, "replay_variance": 0, "replay_method": "FULL_BATCH_REPROCESS"}
        metrics_hash = jcs_sha256(metrics)

        batch = _make_signed_batch(metrics_hash=metrics_hash)

        valid, error, mode = verify_attestation_binding(batch, TEST_PUBKEY_PEM)
        assert valid is True


# ============================================================================
# TEST 6: ECDSA Signature Verification
# ============================================================================

class TestECDSAVerification:

    def test_valid_signature(self):
        data = b"hello world"
        sig = mock_sign(data)
        valid, error = _verify_ecdsa_signature(data, sig, TEST_PUBKEY_PEM)
        assert valid is True

    def test_corrupted_signature(self):
        data = b"hello world"
        sig = mock_sign(data)
        # Corrupt the signature
        sig_bytes = base64.b64decode(sig)
        corrupted = base64.b64encode(sig_bytes[:-1] + bytes([sig_bytes[-1] ^ 0xFF])).decode()
        valid, error = _verify_ecdsa_signature(data, corrupted, TEST_PUBKEY_PEM)
        assert valid is False

    def test_wrong_data(self):
        data = b"hello world"
        sig = mock_sign(data)
        valid, error = _verify_ecdsa_signature(b"goodbye world", sig, TEST_PUBKEY_PEM)
        assert valid is False
