"""Tests for Firebase token validator — mock firebase-admin, no real calls."""

from unittest.mock import MagicMock, patch

from apps.api.src.middleware.firebase_validator import FirebaseTokenValidator


class TestFirebaseValidation:
    def test_successful_validation(self):
        decoded = {
            "sub": "firebase-user-1",
            "tenant_id": "t1",
            "role": "analyst",
            "exp": 9999999999,
            "email": "user@test.com",
        }
        with patch("apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token", return_value=decoded):
            v = FirebaseTokenValidator()
            result = v("firebase.id.token")

        assert result is not None
        assert result["sub"] == "firebase-user-1"
        # derive_tenant_id prefixes non-tenant_ values
        assert result["tenant_id"] == "tenant_t1"
        assert result["role"] == "analyst"

    def test_tenant_derivation_from_uid_hash(self):
        """Token without explicit tenant_id derives tenant from aud:sub hash."""
        decoded = {
            "sub": "firebase-user-1",
            "aud": "intelligent-analyst-enterprise",
            "exp": 9999999999,
            "email": "user@test.com",
        }
        with patch("apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token", return_value=decoded):
            v = FirebaseTokenValidator()
            result = v("firebase.id.token")

        assert result is not None
        assert result["tenant_id"].startswith("tenant_")
        assert len(result["tenant_id"]) > len("tenant_")
        # Default role when no custom claim
        assert result["role"] == "analyst"

    def test_admin_email_gets_tenant_admin_role(self):
        """Email in ADMIN_EMAILS env var gets tenant_admin role."""
        decoded = {
            "sub": "admin-user-1",
            "aud": "intelligent-analyst-enterprise",
            "exp": 9999999999,
            "email": "admin@test.com",
        }
        with patch("apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token", return_value=decoded), \
             patch.dict("os.environ", {"ADMIN_EMAILS": "admin@test.com"}):
            # Reload the allowlist
            import apps.api.src.middleware.firebase_validator as fv
            original = fv._ADMIN_EMAILS
            fv._ADMIN_EMAILS = frozenset({"admin@test.com"})
            try:
                v = FirebaseTokenValidator()
                result = v("admin.token")
            finally:
                fv._ADMIN_EMAILS = original

        assert result is not None
        assert result["role"] == "tenant_admin"

    def test_expired_token_returns_none(self):
        from firebase_admin import auth as fa
        with patch(
            "apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token",
            side_effect=fa.ExpiredIdTokenError("expired", cause=None),
        ):
            v = FirebaseTokenValidator()
            result = v("expired.token")

        assert result is None

    def test_invalid_token_returns_none(self):
        from firebase_admin import auth as fa
        with patch(
            "apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token",
            side_effect=fa.InvalidIdTokenError("bad token"),
        ):
            v = FirebaseTokenValidator()
            result = v("bad.token")

        assert result is None

    def test_missing_sub_returns_none(self):
        decoded = {"tenant_id": "t1", "role": "analyst"}  # No "sub"
        with patch("apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token", return_value=decoded):
            v = FirebaseTokenValidator()
            result = v("no-sub.token")

        assert result is None

    def test_unexpected_error_returns_none(self):
        with patch(
            "apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token",
            side_effect=RuntimeError("unexpected"),
        ):
            v = FirebaseTokenValidator()
            result = v("any.token")

        assert result is None

    def test_custom_app_passed(self):
        mock_app = MagicMock()
        decoded = {"sub": "u1", "tenant_id": "tenant_t1", "role": "analyst"}
        with patch(
            "apps.api.src.middleware.firebase_validator.firebase_auth.verify_id_token",
            return_value=decoded,
        ) as mock_verify:
            v = FirebaseTokenValidator(app=mock_app)
            v("token")
            mock_verify.assert_called_once_with("token", app=mock_app)
