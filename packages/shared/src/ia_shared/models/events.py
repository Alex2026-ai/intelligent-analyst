"""Pub/Sub event schemas.

All events follow the envelope from contracts.md. Each event type has a typed
data payload. Events include version field for forward compatibility.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import EVENT_VERSION


class EventType(str, Enum):
    """All published event types."""

    RESOLUTION_COMPLETED = "resolution.completed"
    REVIEW_DECISION_MADE = "review.decision_made"
    EXPORT_REQUESTED = "export.requested"


# --- Event data payloads ---


class ResolutionCompletedData(BaseModel):
    """Payload for resolution.completed events."""

    model_config = ConfigDict(strict=True)

    resolution_id: str
    document_id: str
    status: str = Field(..., description="resolved | routed_to_review")
    layer_used: int = Field(..., ge=1, le=4)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_chain_id: str
    review_reason: Optional[str] = None


class ReviewDecisionMadeData(BaseModel):
    """Payload for review.decision_made events."""

    model_config = ConfigDict(strict=True)

    case_id: str
    resolution_id: str
    decision: str = Field(
        ...,
        description="approve | reject | escalate | request_more_evidence | reopen",
    )
    decided_by: str
    evidence_chain_id: str


class ExportRequestedData(BaseModel):
    """Payload for export.requested events."""

    model_config = ConfigDict(strict=True)

    export_id: str
    resolution_id: str
    evidence_chain_id: str
    format: str = Field(..., description="pdf | json | csv")
    include_evidence: bool
    include_source_document: bool
    requested_by: str


# --- Event envelope ---


class Event(BaseModel):
    """Pub/Sub event envelope.

    All events follow this structure. Subscribers must tolerate unknown
    event_type values and unknown versions gracefully.
    """

    model_config = ConfigDict(strict=True)

    event_type: EventType
    version: str = EVENT_VERSION
    event_id: str = Field(..., description="UUID of this event")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    tenant_id: str = Field(
        ..., description="Tenant ID — extracted from auth context, never from request body"
    )
    correlation_id: str = Field(..., description="Trace ID for distributed tracing")
    data: ResolutionCompletedData | ReviewDecisionMadeData | ExportRequestedData


class ResolutionCompletedEvent(BaseModel):
    """Typed convenience model for resolution.completed events."""

    model_config = ConfigDict(strict=True)

    event_type: EventType = EventType.RESOLUTION_COMPLETED
    version: str = EVENT_VERSION
    event_id: str
    timestamp: str
    tenant_id: str
    correlation_id: str
    data: ResolutionCompletedData


class ReviewDecisionMadeEvent(BaseModel):
    """Typed convenience model for review.decision_made events."""

    model_config = ConfigDict(strict=True)

    event_type: EventType = EventType.REVIEW_DECISION_MADE
    version: str = EVENT_VERSION
    event_id: str
    timestamp: str
    tenant_id: str
    correlation_id: str
    data: ReviewDecisionMadeData


class ExportRequestedEvent(BaseModel):
    """Typed convenience model for export.requested events."""

    model_config = ConfigDict(strict=True)

    event_type: EventType = EventType.EXPORT_REQUESTED
    version: str = EVENT_VERSION
    event_id: str
    timestamp: str
    tenant_id: str
    correlation_id: str
    data: ExportRequestedData
