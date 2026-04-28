"""Export request and response models.

Models match POST /v1/export and GET /v1/export/{export_id} contracts exactly.
Preconditions enforce INV-004 (human signoff before high-impact export)
and INV-012 (evidence with every artifact).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import SCHEMA_VERSION


class ExportFormat(str, Enum):
    """Supported export artifact formats."""

    PDF = "pdf"
    JSON = "json"
    CSV = "csv"


class ExportStatus(str, Enum):
    """Status of an export job."""

    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


# --- Request model ---


class ExportRequest(BaseModel):
    """Export request submission.

    Maps to POST /v1/export request body.
    Preconditions checked before accepting:
    - Evidence chain must be in 'complete' status
    - High-impact resolutions require human_decision node with 'approve' (INV-004)
    """

    model_config = ConfigDict(strict=True)

    resolution_id: str = Field(..., description="UUID of the resolution to export")
    format: ExportFormat
    include_evidence: bool = Field(
        default=True,
        description="Include evidence chain in export (INV-012)",
    )
    include_source_document: bool = False


# --- Response models ---


class ExportResponse(BaseModel):
    """Export job status response.

    Maps to POST /v1/export 202 Accepted and GET /v1/export/{export_id} 200 OK.
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    export_id: str = Field(..., description="UUID of the export job")
    status: ExportStatus
    format: ExportFormat
    download_url: Optional[str] = Field(
        None,
        description="Signed GCS URL with 15-minute TTL, null until complete",
    )
    error: Optional[str] = None
    estimated_completion_seconds: Optional[int] = Field(
        None, ge=0, description="Estimated seconds to completion, present on 202"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 timestamp")
