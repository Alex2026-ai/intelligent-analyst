"""Review endpoints — GET /v1/review/queue, POST /v1/review/{case_id}/decide.

Requires reviewer+ role.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.src.dependencies import AuthContext, Role, require_role
from ia_shared.models.errors import CASE_ALREADY_DECIDED, NOTES_TOO_SHORT

router = APIRouter(prefix="/v1", tags=["review"])

# In-memory store (replaced by Firestore in production)
_review_store: dict[str, dict] = {}


@router.get("/review/queue")
async def get_review_queue(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    assigned_to: str | None = Query(None),
    cursor: str | None = Query(None),
    page_size: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(require_role(Role.REVIEWER)),
) -> dict:
    """List review cases for the authenticated tenant."""
    # Filter by tenant
    cases = [
        c for c in _review_store.values()
        if c.get("tenant_id") == auth.tenant_id
    ]

    if status:
        cases = [c for c in cases if c.get("status") == status]
    if priority:
        cases = [c for c in cases if c.get("priority") == priority]
    if assigned_to:
        cases = [c for c in cases if c.get("assigned_to") == assigned_to]

    return {
        "cases": cases[:page_size],
        "queue_stats": {
            "total_pending": sum(1 for c in cases if c.get("status") == "pending"),
            "total_assigned": sum(1 for c in cases if c.get("status") == "assigned"),
            "oldest_case_age_hours": 0.0,
            "sla_breaches": 0,
        },
        "next_cursor": None,
    }


@router.post("/review/{case_id}/decide")
async def decide_review(
    case_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(require_role(Role.REVIEWER)),
) -> dict:
    """Submit a reviewer decision on a case."""
    valid_decisions = {"approve", "reject", "escalate", "request_more_evidence", "reopen"}
    decision = body.get("decision")
    if decision not in valid_decisions:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision}")

    notes = body.get("notes", "")
    if len(notes) < 10:
        raise HTTPException(status_code=400, detail="Notes must be at least 10 characters")

    # Check case exists (in production, check Firestore)
    case = _review_store.get(case_id)
    if case is not None and case.get("status") == "decided":
        raise HTTPException(status_code=409, detail="Case already decided")

    now = datetime.now(timezone.utc).isoformat()
    return {
        "case_id": case_id,
        "decision": decision,
        "decided_by": auth.user_id,
        "decided_at": now,
        "evidence_chain_updated": True,
    }
