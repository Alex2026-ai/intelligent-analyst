"""Process reviewer decisions — update evidence chain, case status, events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.api.src.review.exceptions import CaseAlreadyDecidedError, InvalidDecisionError

VALID_DECISIONS = frozenset({"approve", "reject", "escalate", "request_more_evidence", "reopen"})

# Status transitions per decision
DECISION_STATUS_MAP: dict[str, str] = {
    "approve": "decided",
    "reject": "decided",
    "escalate": "escalated",
    "request_more_evidence": "pending",
    "reopen": "pending",
}


def process_decision(
    case: dict[str, Any],
    decision: str,
    reviewer_id: str,
    notes: str,
    evidence_reviewed: list[str] | None = None,
) -> dict[str, Any]:
    """Process a reviewer's decision on a case.

    Args:
        case: The review case dict.
        decision: One of the valid decisions.
        reviewer_id: ID of the reviewer making the decision.
        notes: Required notes (min 10 chars).
        evidence_reviewed: List of evidence node IDs reviewed.

    Returns:
        Decision record dict.

    Raises:
        InvalidDecisionError: If decision is not valid.
        CaseAlreadyDecidedError: If case already has a final decision.
    """
    if decision not in VALID_DECISIONS:
        raise InvalidDecisionError(decision)

    if case.get("status") == "decided":
        raise CaseAlreadyDecidedError(case["case_id"])

    now = datetime.now(timezone.utc).isoformat()

    # Update case status
    new_status = DECISION_STATUS_MAP[decision]
    case["status"] = new_status

    # Build decision record
    return {
        "case_id": case["case_id"],
        "decision": decision,
        "decided_by": reviewer_id,
        "decided_at": now,
        "notes": notes,
        "evidence_reviewed": evidence_reviewed or [],
        "new_status": new_status,
    }


def build_evidence_node_data(decision_record: dict[str, Any]) -> dict[str, Any]:
    """Build data dict for a human_decision evidence node."""
    return {
        "decision": decision_record["decision"],
        "reviewer_id": decision_record["decided_by"],
        "notes": decision_record["notes"],
        "evidence_reviewed": decision_record["evidence_reviewed"],
    }
