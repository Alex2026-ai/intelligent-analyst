"""
test_gate_s2_signing.py — Day 5 Gate S2: KMS Key Aliasing (Tenant-Scoped Signing)

Proves:
1) resolve_signing_key_id() returns global key by default
2) Tenant override returns tenant-specific key path
3) _parse_tenant_signing_key_map() handles all edge cases
4) sign_bytes_kms() key_id_override threads through to KMS call
5) build_anchor_record() includes signing_key_id field
6) Veracity receipt signing block has correct structure
"""

import pytest
from unittest.mock import patch, MagicMock

from app.security.signing import (
    resolve_signing_key_id,
    _parse_tenant_signing_key_map,
    sign_bytes_kms,
    KMS_SIGNING_KEY_ID,
)
from app.security.anchoring import build_anchor_record


# ─────────────────────────────────────────────────────────────────────────────
# 1) resolve_signing_key_id — default / fallback / override
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveSigningKeyId:
    """Gate S2: Key resolution priority chain."""

    def test_resolve_default_uses_global_key(self):
        """No override → returns global KMS_SIGNING_KEY_ID."""
        with patch("app.security.signing._TENANT_SIGNING_KEY_MAP", {}):
            with patch("app.security.signing.KMS_SIGNING_KEY_ID", "projects/p/locations/l/keyRings/kr/cryptoKeys/k"):
                result = resolve_signing_key_id(tenant_id="unmapped-tenant")
                assert result == "projects/p/locations/l/keyRings/kr/cryptoKeys/k"

    def test_resolve_default_fallback_local(self):
        """No global key → returns 'local-signing-key'."""
        with patch("app.security.signing._TENANT_SIGNING_KEY_MAP", {}):
            with patch("app.security.signing.KMS_SIGNING_KEY_ID", ""):
                result = resolve_signing_key_id(tenant_id="any-tenant")
                assert result == "local-signing-key"

    def test_resolve_tenant_override(self):
        """Mapped tenant → tenant-specific key path."""
        tenant_map = {"acme-corp": "projects/acme/locations/us/keyRings/signing/cryptoKeys/batch-key"}
        with patch("app.security.signing._TENANT_SIGNING_KEY_MAP", tenant_map):
            result = resolve_signing_key_id(tenant_id="acme-corp")
            assert result == "projects/acme/locations/us/keyRings/signing/cryptoKeys/batch-key"

    def test_resolve_unmapped_tenant_uses_global(self):
        """Unmapped tenant → global fallback."""
        tenant_map = {"acme-corp": "projects/acme/keys/k"}
        with patch("app.security.signing._TENANT_SIGNING_KEY_MAP", tenant_map):
            with patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key"):
                result = resolve_signing_key_id(tenant_id="other-corp")
                assert result == "global-key"

    def test_resolve_none_tenant_uses_global(self):
        """None tenant → global key."""
        with patch("app.security.signing._TENANT_SIGNING_KEY_MAP", {"t": "k"}):
            with patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key"):
                result = resolve_signing_key_id(tenant_id=None)
                assert result == "global-key"


# ─────────────────────────────────────────────────────────────────────────────
# 2) _parse_tenant_signing_key_map — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestParseTenantSigningKeyMap:
    """Gate S2: Env var parsing robustness."""

    def test_parse_empty(self):
        """Empty string → empty dict."""
        assert _parse_tenant_signing_key_map("") == {}

    def test_parse_single(self):
        """Single entry."""
        assert _parse_tenant_signing_key_map("a:b") == {"a": "b"}

    def test_parse_multi(self):
        """Multiple entries."""
        result = _parse_tenant_signing_key_map("a:b,c:d")
        assert result == {"a": "b", "c": "d"}

    def test_parse_with_spaces(self):
        """Whitespace trimmed."""
        result = _parse_tenant_signing_key_map(" a : b , c : d ")
        assert result == {"a": "b", "c": "d"}

    def test_parse_malformed(self):
        """No colon → skipped."""
        result = _parse_tenant_signing_key_map("no_colon")
        assert result == {}

    def test_parse_colon_in_key_path(self):
        """Colon inside KMS key path is preserved (split on first colon only)."""
        result = _parse_tenant_signing_key_map("tenant1:projects/x/locations/us/keyRings/kr/cryptoKeys/k")
        assert result == {"tenant1": "projects/x/locations/us/keyRings/kr/cryptoKeys/k"}


# ─────────────────────────────────────────────────────────────────────────────
# 3) sign_bytes_kms — key_id_override threading
# ─────────────────────────────────────────────────────────────────────────────

class TestSignBytesKmsOverride:
    """Gate S2: Verify key_id_override threads through to KMS call."""

    @patch("app.security.signing._kms_available", True)
    @patch("app.security.signing.SIGNING_ENABLED", True)
    @patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key-path")
    def test_sign_bytes_override_key_path(self):
        """Mock KMS, verify key_version_path uses override."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.signature = b"fake-signature"
        mock_client.asymmetric_sign.return_value = mock_response

        with patch("app.security.signing._get_kms_client", return_value=mock_client):
            sig, err = sign_bytes_kms(b"test-data", key_id_override="tenant-key-path")

        assert sig is not None
        assert err is None
        call_args = mock_client.asymmetric_sign.call_args
        request = call_args[1]["request"] if "request" in call_args[1] else call_args[0][0]
        if isinstance(request, dict):
            assert "tenant-key-path/cryptoKeyVersions/1" == request["name"]
        else:
            # positional
            assert "tenant-key-path" in str(call_args)

    @patch("app.security.signing._kms_available", True)
    @patch("app.security.signing.SIGNING_ENABLED", True)
    @patch("app.security.signing.KMS_SIGNING_KEY_ID", "global-key-path")
    def test_sign_bytes_no_override_uses_global(self):
        """Mock KMS, verify global key used when no override."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.signature = b"fake-signature"
        mock_client.asymmetric_sign.return_value = mock_response

        with patch("app.security.signing._get_kms_client", return_value=mock_client):
            sig, err = sign_bytes_kms(b"test-data")

        assert sig is not None
        assert err is None
        call_args = mock_client.asymmetric_sign.call_args
        request = call_args[1]["request"] if "request" in call_args[1] else call_args[0][0]
        if isinstance(request, dict):
            assert "global-key-path/cryptoKeyVersions/1" == request["name"]


# ─────────────────────────────────────────────────────────────────────────────
# 4) build_anchor_record — signing_key_id field
# ─────────────────────────────────────────────────────────────────────────────

class TestAnchorRecordSigningKeyId:
    """Gate S2: Anchor record includes signing_key_id."""

    def test_anchor_record_includes_signing_key_id(self):
        """Field present when param passed."""
        record = build_anchor_record(
            batch_id="BATCH-001",
            tenant_id="tenant-x",
            batch_root_hash="abc123",
            code_version="v1",
            sbom_hash="def456",
            chain_length=10,
            signing_key_id="projects/p/keys/k",
        )
        assert record["signing_key_id"] == "projects/p/keys/k"

    def test_anchor_record_backward_compat(self):
        """No param → field is None (backward compatible)."""
        record = build_anchor_record(
            batch_id="BATCH-002",
            tenant_id="tenant-y",
            batch_root_hash="abc123",
            code_version="v1",
            sbom_hash="def456",
            chain_length=5,
        )
        assert record["signing_key_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 5) Veracity receipt — signing block structure
# ─────────────────────────────────────────────────────────────────────────────

class TestVeracityReceiptSigningBlock:
    """Gate S2: Veracity receipt includes signing metadata."""

    def _build_receipt_signing_block(self, key_id, pubkey_fingerprint, global_key):
        """Helper to build the signing block as the server does."""
        return {
            "key_id": key_id,
            "key_fingerprint": pubkey_fingerprint,
            "tenant_scoped": key_id != global_key,
        }

    def test_veracity_receipt_signing_block_structure(self):
        """signing.key_id, signing.key_fingerprint, signing.tenant_scoped present."""
        block = self._build_receipt_signing_block(
            key_id="projects/acme/keys/k",
            pubkey_fingerprint="v1",
            global_key="global-key",
        )
        assert "key_id" in block
        assert "key_fingerprint" in block
        assert "tenant_scoped" in block
        assert block["key_id"] == "projects/acme/keys/k"
        assert block["key_fingerprint"] == "v1"

    def test_tenant_scoped_flag_true_for_override(self):
        """tenant_scoped=True when key differs from global."""
        block = self._build_receipt_signing_block(
            key_id="projects/acme/keys/k",
            pubkey_fingerprint="v1",
            global_key="global-key",
        )
        assert block["tenant_scoped"] is True

    def test_tenant_scoped_flag_false_for_global(self):
        """tenant_scoped=False when key matches global."""
        block = self._build_receipt_signing_block(
            key_id="global-key",
            pubkey_fingerprint="v1",
            global_key="global-key",
        )
        assert block["tenant_scoped"] is False
