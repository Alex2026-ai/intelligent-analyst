"""
test_tenant_encryption_required.py — EU Tenant Key Provisioning: Fail-Closed Tests

Proves:
1) resolve_tenant_key_or_fail() returns key when REQUIRED=true and key exists
2) resolve_tenant_key_or_fail() raises TenantKeyMissingError when REQUIRED=true and key missing
3) resolve_tenant_key_or_fail() delegates to get_or_create_tenant_key when REQUIRED=false
4) Key ID includes -v1 suffix for rotation compatibility
5) TenantKeyMissingError carries tenant_id and tenant_hash attributes
"""

import pytest
from unittest.mock import patch, MagicMock

from app.security.tenant_encryption import (
    resolve_tenant_key_or_fail,
    TenantKeyMissingError,
    _hash_tenant_id,
    _resolve_tenant_key_uncached,
    get_tenant_encryption_status,
    TENANT_KEY_PREFIX,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) resolve_tenant_key_or_fail — REQUIRED=true, key exists
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveRequiredTrueKeyExists:
    """When TENANT_ENCRYPTION_REQUIRED=true and the key exists in KMS."""

    @patch("app.security.tenant_encryption._tenant_key_cache", {})
    @patch("app.security.tenant_encryption.TENANT_ENCRYPTION_REQUIRED", True)
    @patch("app.security.tenant_encryption._kms_available", True)
    @patch("app.security.tenant_encryption.TENANT_KMS_KEYRING", "ia-tenants-eu")
    @patch("app.security.tenant_encryption.KMS_PROJECT", "intelligent-analyst-eu")
    @patch("app.security.tenant_encryption.KMS_LOCATION", "europe-west3")
    def test_returns_key_path_when_key_exists(self):
        """Pre-provisioned key found -> returns (key_path, None)."""
        mock_client = MagicMock()
        mock_client.get_crypto_key.return_value = MagicMock()  # Key exists

        with patch("app.security.tenant_encryption._get_kms_client", return_value=mock_client):
            key_path, error = resolve_tenant_key_or_fail("test-tenant-001")

        assert error is None
        assert key_path is not None
        assert "ia-tenants-eu" in key_path
        assert "-v1" in key_path

        # Verify get_crypto_key was called (not create_crypto_key)
        mock_client.get_crypto_key.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 2) resolve_tenant_key_or_fail — REQUIRED=true, key missing
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveRequiredTrueKeyMissing:
    """When TENANT_ENCRYPTION_REQUIRED=true and the key does NOT exist."""

    @patch("app.security.tenant_encryption._tenant_key_cache", {})
    @patch("app.security.tenant_encryption.TENANT_ENCRYPTION_REQUIRED", True)
    @patch("app.security.tenant_encryption._kms_available", True)
    @patch("app.security.tenant_encryption.TENANT_KMS_KEYRING", "ia-tenants-eu")
    @patch("app.security.tenant_encryption.KMS_PROJECT", "intelligent-analyst-eu")
    @patch("app.security.tenant_encryption.KMS_LOCATION", "europe-west3")
    def test_raises_tenant_key_missing_error(self):
        """Key not found (404) -> raises TenantKeyMissingError."""
        mock_client = MagicMock()
        mock_client.get_crypto_key.side_effect = Exception("404 NOT_FOUND: Key not found")

        with patch("app.security.tenant_encryption._get_kms_client", return_value=mock_client):
            with pytest.raises(TenantKeyMissingError) as exc_info:
                resolve_tenant_key_or_fail("test-tenant-missing")

        assert exc_info.value.tenant_id == "test-tenant-missing"
        assert exc_info.value.tenant_hash == _hash_tenant_id("test-tenant-missing")
        assert "eu_provision_tenant_key.sh" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 3) resolve_tenant_key_or_fail — REQUIRED=false delegates
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveRequiredFalseDelegates:
    """When TENANT_ENCRYPTION_REQUIRED=false, delegates to get_or_create_tenant_key."""

    @patch("app.security.tenant_encryption.TENANT_ENCRYPTION_REQUIRED", False)
    @patch("app.security.tenant_encryption.get_or_create_tenant_key")
    def test_delegates_to_get_or_create(self, mock_get_or_create):
        """REQUIRED=false -> calls get_or_create_tenant_key (existing auto-create behavior)."""
        mock_get_or_create.return_value = ("projects/p/locations/l/keyRings/kr/cryptoKeys/k", None)

        key_path, error = resolve_tenant_key_or_fail("any-tenant")

        mock_get_or_create.assert_called_once_with("any-tenant")
        assert key_path == "projects/p/locations/l/keyRings/kr/cryptoKeys/k"
        assert error is None


# ─────────────────────────────────────────────────────────────────────────────
# 4) Key ID includes -v1 suffix
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyIdV1Suffix:
    """Key IDs include -v1 suffix for future rotation compatibility."""

    @patch("app.security.tenant_encryption._kms_available", True)
    @patch("app.security.tenant_encryption.TENANT_KMS_KEYRING", "ia-tenants-eu")
    @patch("app.security.tenant_encryption.KMS_PROJECT", "intelligent-analyst-eu")
    @patch("app.security.tenant_encryption.KMS_LOCATION", "europe-west3")
    def test_key_id_ends_with_v1(self):
        """_resolve_tenant_key_uncached builds key_id with -v1 suffix."""
        mock_client = MagicMock()
        mock_client.get_crypto_key.return_value = MagicMock()

        with patch("app.security.tenant_encryption._get_kms_client", return_value=mock_client):
            key_path, error = _resolve_tenant_key_uncached("my-tenant", _hash_tenant_id("my-tenant"))

        assert error is None
        # key_path should contain tenant-<hash>-v1
        tenant_hash = _hash_tenant_id("my-tenant")
        expected_key_id = f"{TENANT_KEY_PREFIX}{tenant_hash}-v1"
        assert expected_key_id in key_path


# ─────────────────────────────────────────────────────────────────────────────
# 5) TenantKeyMissingError attributes
# ─────────────────────────────────────────────────────────────────────────────

class TestTenantKeyMissingErrorAttributes:
    """TenantKeyMissingError carries tenant_id and tenant_hash for diagnostics."""

    def test_error_has_tenant_id_and_hash(self):
        """Exception stores tenant_id and tenant_hash."""
        err = TenantKeyMissingError("acme-corp", "abc123def456")
        assert err.tenant_id == "acme-corp"
        assert err.tenant_hash == "abc123def456"
        assert "acme-corp" in str(err)
        assert "abc123def456" in str(err)

    def test_error_message_includes_script_hint(self):
        """Exception message includes provisioning script name for operators."""
        err = TenantKeyMissingError("test-org", "deadbeef")
        assert "eu_provision_tenant_key.sh" in str(err)


# ─────────────────────────────────────────────────────────────────────────────
# 6) get_tenant_encryption_status includes required field
# ─────────────────────────────────────────────────────────────────────────────

class TestEncryptionStatusRequired:
    """Status endpoint reports the required flag."""

    @patch("app.security.tenant_encryption.TENANT_ENCRYPTION_REQUIRED", True)
    def test_status_includes_required_true(self):
        status = get_tenant_encryption_status()
        assert "required" in status
        assert status["required"] is True

    @patch("app.security.tenant_encryption.TENANT_ENCRYPTION_REQUIRED", False)
    def test_status_includes_required_false(self):
        status = get_tenant_encryption_status()
        assert "required" in status
        assert status["required"] is False
