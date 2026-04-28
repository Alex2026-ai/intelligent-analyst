"""Review queue and decision models.

Models match GET /v1/review/queue and POST /v1/review/{case_id}/decide contracts exactly.
Review routing enforces fail-closed on ambiguity (INV-003).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_REVIEW_NOTES_LENGTH,
    SCHEMA_VERSION,
)


class CaseStatus(str, Enum):
    """Status of a review case in the queue."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    DECIDED = "decided"
    ESCALATED = "escalated"


class CasePriority(str, Enum):
    """Priority of a review case."""

    STANDARD = "standard"
    HIGH = "high"
    URGENT = "urgent"


class ReviewReason(str, Enum):
    """Reason a resolution was routed to review (INV-003: fail-closed)."""

    LOW_CONFIDENCE = "low_confidence"
    HIGH_IMPACT = "high_impact"
    FORCE_REVIEW = "force_review"
    LLM_UNAVAILABLE = "llm_unavailable"


class Decision(str, Enum):
    """Possible reviewer decisions on a case."""

    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    REOPEN = "reopen"


# --- Request models ---


class ReviewDecisionRequest(BaseModel):
    """Reviewer decision submission.

    Maps to POST /v1/review/{case_id}/decide request body.
    Notes must be at least 10 characters (contracts.md).
    """

    model_config = ConfigDict(strict=True)

    decision: Decision
    notes: str = Field(..., min_length=MIN_REVIEW_NOTES_LENGTH)
    evidence_reviewed: list[str] = Field(
        default_factory=list,
        description="List of evidence node IDs reviewed",
    )


class ReviewQueueParams(BaseModel):
    """Query parameters for review queue listing."""

    model_config = ConfigDict(strict=True)

    status: Optional[CaseStatus] = None
    priority: Optional[CasePriority] = None
    assigned_to: Optional[str] = None
    cursor: Optional[str] = None
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


# --- Response models ---


class ReviewCase(BaseModel):
    """A single review case in the queue.

    Storable model — includes tenant_id (extracted from token, INV-005)
    and _schema_version.
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    case_id: str = Field(..., description="UUID of the review case")
    resolution_id: str = Field(..., description="UUID of the associated resolution")
    evidence_chain_id: str = Field(..., description="UUID of the evidence chain")
    status: CaseStatus
    priority: CasePriority
    review_reason: ReviewReason
    assigned_to: Optional[str] = Field(
        None, description="User ID of assigned reviewer"
    )
    sla_deadline: str = Field(..., description="ISO 8601 timestamp — SLA breach deadline")
    created_at: str = Field(..., description="ISO 8601 timestamp")


class QueueStats(BaseModel):
    """Aggregate statistics for the review queue."""

    model_config = ConfigDict(strict=True)

    total_pending: int = Field(..., ge=0)
    total_assigned: int = Field(..., ge=0)
    oldest_case_age_hours: float = Field(..., ge=0.0)
    sla_breaches: int = Field(..., ge=0)


class ReviewQueueResponse(BaseModel):
    """Review queue listing response.

    Maps to GET /v1/review/queue 200 OK response.
    """

    model_config = ConfigDict(strict=True)

    cases: list[ReviewCase]
    queue_stats: QueueStats
    next_cursor: Optional[str] = None


class ReviewDecisionResponse(BaseModel):
    """Response after a reviewer submits a decision.

    Maps to POST /v1/review/{case_id}/decide 200 OK response.
    decided_by is extracted from the JWT token (INV-005).
    """

    model_config = ConfigDict(strict=True)

    case_id: str
    decision: Decision
    decided_by: str = Field(
        ..., description="User ID — extracted from token, never from request body"
    )
    decided_at: str = Field(..., description="ISO 8601 timestamp")
    evidence_chain_updated: bool
