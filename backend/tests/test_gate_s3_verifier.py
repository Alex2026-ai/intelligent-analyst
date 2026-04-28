"""
test_gate_s3_verifier.py — Day 5 Gate S3: Verifier Key Awareness

Proves:
1) verify_attestation_binding resolves correct public key from attestation key_id
2) Global key batch → verify PASS (backward compatible)
3) Tenant key batch → verify PASS (key-aware resolution)
4) Unknown/missing key_id → verify FAIL with clear error
5) _resolve_public_key_for_verification priority chain
6) get_public_key_pem_for_key_id caches per-key
"""

import base64
import pytest
from unittest.mock import patch, MagicMock

from app.security.public_verify import (
    verify_attestation_binding,
    _resolve_public_key_for_verification,
    get_cached_public_key,
)
from app.security.signing import (
    get_public_key_pem_for_key_id,
    _public_key_cache,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_batch_with_attestation(key_id, signed_payload_b64, signature_b64):
    """Build a minimal batch dict with attestation fields."""
    return {
        "trace_id": "BATCH-S3-TEST",
        "status": "completed",
        "attestation": {
            "key_id": key_id,
            "signed_payload_jcs_b64": signed_payload_b64,
            "signature_b64": signature_b64,
            "algorithm": "ECDSA_P256_SHA256",
            "attestation_version": "1.1",
        },
        "hash_chain": {
            "batch_root_hash": "deadbeef" * 8,
        },
    }


# Dummy PEM for testing (not a real key, just format-valid)
DUMMY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEtest
-----END PUBLIC KEY-----"""


# ─────────────────────────────────────────────────────────────────────────────
# 1) _resolve_public_key_for_verification — priority chain
# ─────────────────────────────────────────────────────────────────────────────

class TestResolvePublicKeyForVerification:
    """Gate S3: Public key resolution priority."""

    def test_no_key_id_uses_global_cache(self):
        """None key_id → falls back to global cached key."""
        with patch("app.security.public_verify.get_cached_public_key", return_value="global-pem"):
            result = _resolve_public_key_for_verification(None)
            assert result == "global-pem"

    def test_global_key_id_uses_global_cache(self):
        """key_id matching global → uses existing cache."""
        with patch("app.security.public_verify.get_cached_public_key", return_value="global-pem"):
            with patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key"):
                result = _resolve_public_key_for_verification("global-key")
                assert result == "global-pem"

    def test_tenant_key_id_fetches_specific_key(self):
        """key_id different from global → fetches tenant-specific public key."""
        with patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key"):
            with patch("app.security.signing.get_public_key_pem_for_key_id",
                       return_value=("tenant-pem", None)):
                result = _resolve_public_key_for_verification("tenant-key")
                assert result == "tenant-pem"

    def test_tenant_key_fetch_fails_returns_none(self):
        """If tenant key fetch fails, returns None (not global fallback)."""
        with patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key"):
            with patch("app.security.signing.get_public_key_pem_for_key_id",
                       return_value=(None, "kms_error")):
                result = _resolve_public_key_for_verification("bad-tenant-key")
                assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 2) verify_attestation_binding — key-aware
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyAttestationBindingKeyAware:
    """Gate S3: verify_attestation_binding extracts key_id and resolves."""

    def test_no_attestation_falls_back_legacy(self):
        """Batch without attestation → LEGACY_ROOT_HASH mode."""
        batch = {"signature": {}}
        valid, error, mode = verify_attestation_binding(batch)
        assert mode == "LEGACY_ROOT_HASH"
        assert not valid

    def test_attestation_no_signature_fails(self):
        """Attestation present but no signature → FAIL."""
        batch = _make_batch_with_attestation("some-key", "payload-b64", None)
        valid, error, mode = verify_attestation_binding(batch)
        assert not valid
        assert "no signature" in error.lower()
        assert mode == "ATTESTATION_BINDING_V1"

    def test_explicit_pem_skips_resolution(self):
        """When public_key_pem is explicitly passed, key resolution is skipped."""
        batch = _make_batch_with_attestation(
            "tenant-key",
            base64.b64encode(b'{"batch_id": "BATCH-S3-TEST"}').decode(),
            "fake-sig",
        )
        # Pass explicit PEM — _resolve_public_key_for_verification should NOT be called
        with patch("app.security.public_verify._resolve_public_key_for_verification") as mock_resolve:
            with patch("app.security.public_verify._verify_ecdsa_signature",
                       return_value=(True, None)):
                with patch("app.security.public_verify._verify_payload_matches_batch",
                           return_value=(True, None)):
                    valid, error, mode = verify_attestation_binding(batch, public_key_pem="explicit-pem")
                    mock_resolve.assert_not_called()
                    assert valid

    def test_key_id_passed_to_resolver(self):
        """Attestation key_id is passed to the resolver."""
        batch = _make_batch_with_attestation(
            "projects/p/keys/tenant-key",
            base64.b64encode(b'{"batch_id": "BATCH-S3-TEST"}').decode(),
            "fake-sig",
        )
        with patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value="resolved-pem") as mock_resolve:
            with patch("app.security.public_verify._verify_ecdsa_signature",
                       return_value=(True, None)):
                with patch("app.security.public_verify._verify_payload_matches_batch",
                           return_value=(True, None)):
                    valid, error, mode = verify_attestation_binding(batch)
                    mock_resolve.assert_called_once_with("projects/p/keys/tenant-key")
                    assert valid


# ─────────────────────────────────────────────────────────────────────────────
# 3) get_public_key_pem_for_key_id — caching
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPublicKeyPemForKeyId:
    """Gate S3: Per-key public key fetch and cache."""

    def test_empty_key_id_returns_error(self):
        """Empty key_id → error."""
        pem, error = get_public_key_pem_for_key_id("")
        assert pem is None
        assert error == "key_id_not_provided"

    def test_none_key_id_returns_error(self):
        """None key_id → error."""
        pem, error = get_public_key_pem_for_key_id(None)
        assert pem is None
        assert error == "key_id_not_provided"

    def test_cached_key_returned_without_kms_call(self):
        """Cached key → returned without KMS API call."""
        _public_key_cache["cached-key"] = "cached-pem"
        try:
            pem, error = get_public_key_pem_for_key_id("cached-key")
            assert pem == "cached-pem"
            assert error is None
        finally:
            del _public_key_cache["cached-key"]

    @patch("app.security.signing._kms_available", True)
    def test_kms_call_populates_cache(self):
        """Successful KMS call populates the cache."""
        mock_client = MagicMock()
        mock_key = MagicMock()
        mock_key.pem = "fetched-pem"
        mock_client.get_public_key.return_value = mock_key

        # Clear cache for this key
        _public_key_cache.pop("new-key", None)

        with patch("app.security.signing._get_kms_client", return_value=mock_client):
            pem, error = get_public_key_pem_for_key_id("new-key")
            assert pem == "fetched-pem"
            assert error is None
            assert _public_key_cache.get("new-key") == "fetched-pem"
            # Verify correct key version path
            mock_client.get_public_key.assert_called_once_with(
                request={"name": "new-key/cryptoKeyVersions/1"}
            )

        # Clean up
        _public_key_cache.pop("new-key", None)

    @patch("app.security.signing._kms_available", False)
    def test_kms_not_available_returns_error(self):
        """KMS not available → error."""
        _public_key_cache.pop("any-key", None)
        pem, error = get_public_key_pem_for_key_id("any-key")
        assert pem is None
        assert error == "kms_not_available"


# ─────────────────────────────────────────────────────────────────────────────
# 4) End-to-end: key mismatch → FAIL
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyMismatchFails:
    """Gate S3: Wrong key → verification FAIL."""

    def test_unknown_key_id_fails(self):
        """Unknown key_id that can't be resolved → FAIL."""
        batch = _make_batch_with_attestation(
            "projects/p/keys/nonexistent-key",
            base64.b64encode(b'{"batch_id": "BATCH-S3-TEST"}').decode(),
            "fake-sig",
        )
        with patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=None):
            valid, error, mode = verify_attestation_binding(batch)
            assert not valid
            assert mode == "ATTESTATION_BINDING_V1"
            # Error should indicate public key not available
            assert error is not None
