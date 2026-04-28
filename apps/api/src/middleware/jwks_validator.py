"""JWKS-based JWT validator for production use.

Fetches public keys from the identity provider's JWKS endpoint,
caches them with TTL, and validates RS256 tokens.
Fail-closed: any error results in token rejection.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)


class JWKSTokenValidator:
    """Validates JWTs against a JWKS endpoint.

    - Fetches and caches JWKS keys with configurable TTL
    - Validates RS256 signatures
    - Extracts claims: sub, tenant_id, role, exp
    - Fail-closed: any error returns None (token rejected)
    """

    def __init__(
        self,
        jwks_url: str,
        audience: str = "",
        issuer: str = "",
        cache_ttl_seconds: int = 300,
        algorithms: list[str] | None = None,
    ) -> None:
        if not jwks_url:
            raise ValueError("jwks_url is required for production token validation")

        self._jwks_url = jwks_url
        self._audience = audience
        self._issuer = issuer
        self._algorithms = algorithms or ["RS256"]
        self._jwk_client = PyJWKClient(
            jwks_url, cache_jwk_set=True, lifespan=cache_ttl_seconds
        )

    def __call__(self, token: str) -> dict[str, Any] | None:
        """Validate a JWT token and return claims.

        Returns None on ANY failure (fail-closed).
        """
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)

            decode_kwargs: dict[str, Any] = {
                "key": signing_key.key,
                "algorithms": self._algorithms,
            }

            if self._audience:
                decode_kwargs["audience"] = self._audience
            if self._issuer:
                decode_kwargs["issuer"] = self._issuer

            claims = jwt.decode(token, **decode_kwargs)
            return claims

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired", extra={"jwks_url": self._jwks_url})
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", str(e))
            return None
        except PyJWKClientError as e:
            logger.error("JWKS fetch failed (fail-closed): %s", str(e))
            return None
        except Exception as e:
            logger.error("Unexpected auth error (fail-closed): %s", str(e))
            return None
