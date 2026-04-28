"""
internal_system_vitals.py — Day 6: Admin-only system observability endpoint.

GET /internal/system-vitals
  - Requires Firebase admin claim — no bypass, no API key fallback
  - Returns p95 latencies, cache rates, failover rate, ledger integrity
"""

from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()


async def require_firebase_admin_claim(request: Request):
    """
    Firebase-only admin auth for internal endpoints. Fail-closed.

    1. Extract Authorization: Bearer <token> → 401 if missing
    2. Firebase Admin SDK must be available → 503 if not
    3. verify_id_token → 401 if invalid/expired
    4. derive_role → is_admin_role → 403 if not admin
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    token = auth_header[7:]

    # Function-level imports to avoid circular deps
    try:
        from app.server_enterprise_golden import (
            HAS_FIREBASE_AUTH,
            derive_role,
            is_admin_role,
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Server module unavailable")

    if not HAS_FIREBASE_AUTH:
        raise HTTPException(status_code=503, detail="Firebase Admin SDK not available")

    try:
        from firebase_admin import auth as firebase_auth
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    role = derive_role(decoded)
    if not is_admin_role(role):
        raise HTTPException(status_code=403, detail="Admin role required")

    return {"role": role, "uid": decoded.get("uid", "")}


@router.get("/internal/system-vitals")
async def system_vitals(identity: dict = Depends(require_firebase_admin_claim)):
    """Return aggregated system observability metrics."""
    # Function-level import to avoid circular deps
    from app.server_enterprise_golden import _firestore_db
    from app.metrics.system_metrics import get_system_vitals

    return get_system_vitals(_firestore_db)
