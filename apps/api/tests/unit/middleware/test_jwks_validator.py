"""Tests for JWKS-based JWT validator — mock JWKS, no real calls."""

from unittest.mock import MagicMock, patch

import pytest

from apps.api.src.middleware.jwks_validator import JWKSTokenValidator


class TestJWKSValidatorInit:
    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="jwks_url is required"):
            JWKSTokenValidator(jwks_url="")

    def test_valid_url_accepted(self):
        with patch("apps.api.src.middleware.jwks_validator.PyJWKClient"):
            v = JWKSTokenValidator(jwks_url="https://idp.example.com/.well-known/jwks.json")
            assert v is not None


class TestJWKSValidation:
    def _make_validator(self, **kwargs):
        with patch("apps.api.src.middleware.jwks_validator.PyJWKClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            v = JWKSTokenValidator(jwks_url="https://idp.example.com/jwks", **kwargs)
            return v, mock_client

    def test_successful_validation(self):
        v, mock_client = self._make_validator()
        mock_key = MagicMock()
        mock_key.key = "test-public-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_key

        expected_claims = {"sub": "user-1", "tenant_id": "t1", "role": "analyst", "exp": 9999999999}
        with patch("apps.api.src.middleware.jwks_validator.jwt.decode", return_value=expected_claims):
            result = v("fake.jwt.token")

        assert result == expected_claims
        assert result["sub"] == "user-1"

    def test_expired_token_returns_none(self):
        import jwt as pyjwt
        v, mock_client = self._make_validator()
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("apps.api.src.middleware.jwks_validator.jwt.decode", side_effect=pyjwt.ExpiredSignatureError):
            result = v("expired.jwt.token")

        assert result is None

    def test_invalid_token_returns_none(self):
        import jwt as pyjwt
        v, mock_client = self._make_validator()
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("apps.api.src.middleware.jwks_validator.jwt.decode", side_effect=pyjwt.InvalidTokenError("bad")):
            result = v("invalid.jwt.token")

        assert result is None

    def test_jwks_fetch_failure_returns_none(self):
        from jwt import PyJWKClientError
        v, mock_client = self._make_validator()
        mock_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("Network error")

        result = v("any.jwt.token")
        assert result is None

    def test_unexpected_error_returns_none(self):
        v, mock_client = self._make_validator()
        mock_client.get_signing_key_from_jwt.side_effect = RuntimeError("Something unexpected")

        result = v("any.jwt.token")
        assert result is None

    def test_audience_passed_to_decode(self):
        v, mock_client = self._make_validator(audience="my-app")
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("apps.api.src.middleware.jwks_validator.jwt.decode", return_value={"sub": "u1"}) as mock_decode:
            v("token")
            call_kwargs = mock_decode.call_args[1]
            assert call_kwargs["audience"] == "my-app"

    def test_issuer_passed_to_decode(self):
        v, mock_client = self._make_validator(issuer="https://idp.example.com")
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("apps.api.src.middleware.jwks_validator.jwt.decode", return_value={"sub": "u1"}) as mock_decode:
            v("token")
            call_kwargs = mock_decode.call_args[1]
            assert call_kwargs["issuer"] == "https://idp.example.com"
