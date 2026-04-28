"""Case routing — creates review cases from resolver routing decisions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from apps.api.src.review.sla import compute_sla_deadline

# Priority mapping from routing reason
REASON_TO_PRIORITY: dict[str, str] = {
    "high_impact": "high",
    "force_review": "standard",
    "low_confidence": "standard",
    "llm_unavailable": "high",
}


def create_review_case(
    resolution_id: str,
    evidence_chain_id: str,
    review_reason: str,
    sla_hours_override: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Create a review case from a resolver routing decision.

    Args:
        resolution_id: UUID of the resolution.
        evidence_chain_id: UUID of the evidence chain.
        review_reason: Reason for routing (from resolver).
        sla_hours_override: Per-tenant SLA hours.

    Returns:
        Review case dict ready for storage.
    """
    priority = REASON_TO_PRIORITY.get(review_reason, "standard")
    now = datetime.now(timezone.utc).isoformat()
    sla_deadline = compute_sla_deadline(priority, now, sla_hours_override)

    return {
        "case_id": str(uuid.uuid4()),
        "resolution_id": resolution_id,
        "evidence_chain_id": evidence_chain_id,
        "status": "pending",
        "priority": priority,
        "review_reason": review_reason,
        "assigned_to": None,
        "sla_deadline": sla_deadline,
        "created_at": now,
        "reassignment_count": 0,
    }
