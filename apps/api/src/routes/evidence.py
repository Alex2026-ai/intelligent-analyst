"""Evidence endpoints — GET /v1/evidence/{chain_id}.

Requires analyst+ role. Tenant-scoped (INV-005).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.src.dependencies import AuthContext, Role, require_role
from apps.api.src.middleware.tenant import verify_tenant_access

router = APIRouter(prefix="/v1", tags=["evidence"])

# In-memory store (replaced by Firestore in production)
_evidence_store: dict[str, dict] = {}


@router.get("/evidence/{chain_id}")
async def get_evidence_chain(
    chain_id: str,
    cursor: str | None = Query(None),
    page_size: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Retrieve an evidence chain by ID."""
    chain = _evidence_store.get(chain_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Evidence chain not found")

    # Tenant isolation (INV-005)
    if not verify_tenant_access(auth, chain.get("tenant_id", "")):
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")

    return chain
