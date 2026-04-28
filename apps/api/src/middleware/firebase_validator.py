"""Firebase Auth token validator.

Uses firebase-admin SDK to verify ID tokens.
Derives tenant_id and role server-side from token claims — matches
the monolith's derive_tenant_id() and derive_role() logic so that
dashboard Firebase tokens work identically against PRE.
Fail-closed: any error results in token rejection.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth

logger = logging.getLogger(__name__)

# Admin email allowlist — same env var as monolith (ADMIN_EMAILS)
_ADMIN_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
)

# Valid roles — matches monolith VALID_ROLES
_VALID_ROLES = {"user", "auditor", "admin", "viewer", "platform_admin",
                "analyst", "reviewer", "tenant_admin"}


def _derive_tenant_id(decoded: dict[str, Any]) -> str:
    """Derive tenant_id server-side from Firebase token.

    Priority:
    1. Explicit 'tenant_id' custom claim
    2. Stable hash of aud (project) + sub (uid)

    Matches monolith derive_tenant_id() exactly.
    """
    explicit = decoded.get("tenant_id")
    if explicit and isinstance(explicit, str) and len(explicit) > 0:
        return explicit if explicit.startswith("tenant_") else f"tenant_{explicit}"

    uid = decoded.get("sub", "")
    aud = decoded.get("aud", "")
    if uid:
        stable_input = f"{aud}:{uid}"
        tenant_hash = hashlib.sha256(stable_input.encode()).hexdigest()[:16]
        return f"tenant_{tenant_hash}"

    return ""


def _derive_role(decoded: dict[str, Any]) -> str:
    """Derive role server-side from Firebase token.

    Priority:
    1. Email in admin allowlist -> 'tenant_admin'
    2. Explicit 'role' custom claim if valid
    3. Fallback: 'analyst' (lowest PRE role that can read batches)

    Maps monolith 'admin' -> PRE 'tenant_admin' and 'user' -> 'analyst'
    since PRE uses the architecture-standard role enum.
    """
    email = (decoded.get("email") or "").lower()
    if email and email in _ADMIN_EMAILS:
        return "tenant_admin"

    role = decoded.get("role", "")
    if role in _VALID_ROLES:
        # Map monolith role names to PRE equivalents
        if role == "admin":
            return "tenant_admin"
        if role == "user":
            return "analyst"
        return role

    return "analyst"


class FirebaseTokenValidator:
    """Validates Firebase ID tokens.

    Requires firebase-admin to be initialized with credentials.
    Derives tenant_id and role server-side (never trusts client claims).
    Fail-closed: any error returns None.
    """

    def __init__(self, app: firebase_admin.App | None = None) -> None:
        self._app = app

    def __call__(self, token: str) -> dict[str, Any] | None:
        """Validate a Firebase ID token. Fail-closed on any error."""
        try:
            decoded = firebase_auth.verify_id_token(token, app=self._app)

            if not decoded.get("sub"):
                logger.warning("Firebase token missing sub claim")
                return None

            tenant_id = _derive_tenant_id(decoded)
            role = _derive_role(decoded)

            if not tenant_id or not role:
                logger.warning("Could not derive tenant_id or role from Firebase token")
                return None

            return {
                "sub": decoded["sub"],
                "tenant_id": tenant_id,
                "role": role,
                "exp": decoded.get("exp"),
                "email": decoded.get("email", ""),
            }
        except firebase_auth.ExpiredIdTokenError:
            logger.warning("Firebase token expired")
            return None
        except firebase_auth.InvalidIdTokenError as e:
            logger.warning("Invalid Firebase token: %s", str(e))
            return None
        except Exception as e:
            logger.error("Unexpected Firebase auth error (fail-closed): %s", str(e))
            return None
