"""Resolution request and response models.

Models match POST /v1/resolve and POST /v1/resolve/batch contracts exactly.
tenant_id is extracted from JWT token — never appears in request bodies (INV-005).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import (
    DEFAULT_BATCH_PARALLEL,
    MAX_BATCH_PARALLEL,
    MAX_BATCH_SIZE,
    MAX_CONFIDENCE,
    MAX_DOCUMENT_CONTENT_BYTES,
    MIN_CONFIDENCE,
    SCHEMA_VERSION,
)


class DocumentType(str, Enum):
    """Supported document types for resolution."""

    REGULATORY = "regulatory"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    MEDICAL = "medical"


class Priority(str, Enum):
    """Resolution priority levels."""

    STANDARD = "standard"
    HIGH = "high"
    URGENT = "urgent"


class ResolutionStatus(str, Enum):
    """Outcome status of a resolution."""

    RESOLVED = "resolved"
    ROUTED_TO_REVIEW = "routed_to_review"


class BatchItemStatus(str, Enum):
    """Status of an individual item within a batch resolution."""

    RESOLVED = "resolved"
    ROUTED_TO_REVIEW = "routed_to_review"
    FAILED = "failed"


class ReviewReason(str, Enum):
    """Reason a resolution was routed to human review (INV-003: fail-closed)."""

    LOW_CONFIDENCE = "low_confidence"
    HIGH_IMPACT = "high_impact"
    FORCE_REVIEW = "force_review"
    LLM_UNAVAILABLE = "llm_unavailable"


# --- Request models (no tenant_id — extracted from token) ---


class DocumentMetadata(BaseModel):
    """Optional metadata accompanying a document submission."""

    model_config = ConfigDict(strict=True)

    source: Optional[str] = None
    priority: Priority = Priority.STANDARD
    force_review: bool = False


class ResolutionRequest(BaseModel):
    """Single document resolution request.

    Maps to POST /v1/resolve request body. Idempotency-Key is a required header,
    not part of the body.
    """

    model_config = ConfigDict(strict=True)

    document_id: str = Field(
        ..., description="UUID identifying the document", pattern=r"^[0-9a-f\-]{36}$"
    )
    document_type: DocumentType
    content: str = Field(
        ..., description="Document text", max_length=MAX_DOCUMENT_CONTENT_BYTES
    )
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class BatchConfig(BaseModel):
    """Configuration for batch resolution processing."""

    model_config = ConfigDict(strict=True)

    max_parallel: int = Field(
        default=DEFAULT_BATCH_PARALLEL, ge=1, le=MAX_BATCH_PARALLEL
    )
    stop_on_error: bool = False


class BatchResolutionRequest(BaseModel):
    """Batch document resolution request.

    Maps to POST /v1/resolve/batch request body. Maximum 100 documents per batch.
    Idempotency-Key is a required header, not part of the body.
    """

    model_config = ConfigDict(strict=True)

    documents: list[ResolutionRequest] = Field(
        ..., min_length=1, max_length=MAX_BATCH_SIZE
    )
    batch_config: BatchConfig = Field(default_factory=BatchConfig)


# --- Response models ---


class ResolutionResponse(BaseModel):
    """Single document resolution response.

    Maps to POST /v1/resolve 200 OK response. Includes evidence_chain_id
    for full lineage traceability (INV-002).
    """

    model_config = ConfigDict(strict=True)

    resolution_id: str = Field(..., description="UUID of the resolution record")
    status: ResolutionStatus
    layer_used: int = Field(..., ge=1, le=4, description="Resolution layer (1-4)")
    confidence: float = Field(
        ..., ge=MIN_CONFIDENCE, le=MAX_CONFIDENCE
    )
    resolution: Optional[str] = Field(
        None, description="Resolution text, null if routed to review"
    )
    review_reason: Optional[ReviewReason] = None
    evidence_chain_id: str = Field(
        ..., description="UUID of the evidence chain (INV-002)"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp")


class BatchResultItem(BaseModel):
    """Result for a single document within a batch response."""

    model_config = ConfigDict(strict=True)

    document_id: str
    resolution_id: str
    status: BatchItemStatus
    layer_used: Optional[int] = Field(None, ge=1, le=4)
    confidence: Optional[float] = Field(
        None, ge=MIN_CONFIDENCE, le=MAX_CONFIDENCE
    )
    error: Optional[str] = None


class BatchResolutionResponse(BaseModel):
    """Batch resolution response.

    Maps to POST /v1/resolve/batch 200 OK response.
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    batch_id: str = Field(..., description="UUID of the batch")
    total: int = Field(..., ge=0)
    resolved: int = Field(..., ge=0)
    routed_to_review: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BatchResultItem]
    created_at: str = Field(..., description="ISO 8601 timestamp")
