"""Evidence chain and node models.

Models match GET /v1/evidence/{chain_id} contract exactly.
Every resolution must have an unbroken evidence chain (INV-002).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ia_shared.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SCHEMA_VERSION


class NodeType(str, Enum):
    """Types of evidence nodes in a chain."""

    SOURCE_ARTIFACT = "source_artifact"
    RETRIEVAL_RESULT = "retrieval_result"
    TRANSFORMATION = "transformation"
    MODEL_CALL = "model_call"
    HUMAN_DECISION = "human_decision"
    EXPORT_ARTIFACT = "export_artifact"
    DEGRADATION_EVENT = "degradation_event"


class ChainStatus(str, Enum):
    """Status of an evidence chain."""

    BUILDING = "building"
    COMPLETE = "complete"
    INTEGRITY_WARNING = "integrity_warning"


class EvidenceNode(BaseModel):
    """A single node in an evidence chain.

    Each node represents one step in the resolution process,
    maintaining full lineage traceability (INV-002).
    """

    model_config = ConfigDict(strict=True)

    node_id: str = Field(..., description="UUID of this evidence node")
    node_type: NodeType
    sequence: int = Field(..., ge=1, description="Position in the chain (1-indexed)")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    node_hash: str = Field(..., description="SHA-256 hash of this node's content")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-specific payload data",
    )


class EvidenceChain(BaseModel):
    """Complete evidence chain for a resolution.

    Maps to GET /v1/evidence/{chain_id} 200 OK response.
    Supports pagination via cursor for large chains.
    """

    model_config = ConfigDict(strict=True)

    _schema_version: str = SCHEMA_VERSION

    chain_id: str = Field(..., description="UUID of the evidence chain")
    resolution_id: str = Field(..., description="UUID of the associated resolution")
    tenant_id: str = Field(
        ...,
        description="Tenant ID — extracted from token, never from request body (INV-005)",
    )
    status: ChainStatus
    chain_hash: str = Field(..., description="SHA-256 hash of the complete chain")
    nodes: list[EvidenceNode] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(
        None, description="Pagination cursor for next page, null if last page"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp")
    updated_at: str = Field(..., description="ISO 8601 timestamp")


class EvidenceQueryParams(BaseModel):
    """Query parameters for evidence chain retrieval."""

    model_config = ConfigDict(strict=True)

    cursor: Optional[str] = None
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
