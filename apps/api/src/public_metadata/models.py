"""Domain objects for the Public Metadata Controller.

Versioned contracts: PublicMetadataPolicy, PublicMetadataDecision, PublicAuthoritySample.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PolicyMode(str, Enum):
    """How the policy governs sample emission."""
    DENY_ALL = "deny_all"
    CURATED_HYBRID = "curated_hybrid"
    AUTO_SANITIZED = "auto_sanitized"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_WITH_REDACTION_PROFILE = "allow_with_redaction_profile"
    REQUIRES_MANUAL_APPROVAL = "requires_manual_approval"


class ManualApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SampleStatus(str, Enum):
    """Canonical lifecycle: draft → approved → published → revoked.

    - draft: emitted candidate, pending review
    - approved: admin approved, not yet publicly visible
    - published: visible on public read endpoints
    - revoked: permanently removed from public endpoints
    """
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    REVOKED = "revoked"


class FieldAction(str, Enum):
    """What to do with a source field during derivation."""
    PUBLIC = "public"
    REDACT = "redact"
    GENERALIZE = "generalize"
    HASH_ONLY = "hash_only"
    DROP = "drop"
    MANUAL_REVIEW = "manual_review"


class OutcomeClass(str, Enum):
    """High-level outcome classification safe for public display."""
    RESOLVED = "resolved"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    COMPLIANCE_FLAG = "compliance_flag"
    RISK_ASSESSMENT = "risk_assessment"


# ---------------------------------------------------------------------------
# PublicMetadataPolicy
# ---------------------------------------------------------------------------

class PublicMetadataPolicy(BaseModel):
    """Versioned policy governing public sample derivation (PMC-INV-002)."""

    model_config = ConfigDict(strict=True)

    policy_id: str
    version: str
    mode: PolicyMode
    allow_real_sanitized_samples: bool = False
    require_manual_approval: bool = True
    public_anchor_allowlist: list[str] = Field(
        default_factory=lambda: ["INV-002", "INV-005", "INV-006"]
    )
    blocked_tenants: list[str] = Field(default_factory=list)
    _schema_version: str = "1.0"


# ---------------------------------------------------------------------------
# PublicMetadataDecision
# ---------------------------------------------------------------------------

class PublicMetadataDecision(BaseModel):
    """Result of evaluating a resolution for public derivation eligibility."""

    model_config = ConfigDict(strict=True)

    decision_id: str
    source_resolution_id: str
    tenant_id: str
    policy_version: str
    decision: Decision
    manual_approval_required: bool = False
    manual_approval_status: ManualApprovalStatus = ManualApprovalStatus.NOT_REQUIRED
    dropped_fields: list[str] = Field(default_factory=list)
    generalized_fields: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    created_at: str
    integrity_hash: str


# ---------------------------------------------------------------------------
# PublicAuthoritySample
# ---------------------------------------------------------------------------

class PublicAuthoritySample(BaseModel):
    """A public-safe derivation of a resolution story (PMC-INV-001, PMC-INV-004).

    Contains ONLY sanitized, policy-approved content.
    No tenant IDs, no names, no raw evidence, no internal references.
    """

    model_config = ConfigDict(strict=True)

    public_sample_id: str
    sample_type: str = "resolution_authority"
    status: SampleStatus = SampleStatus.DRAFT
    headline: str
    summary: str
    outcome_class: OutcomeClass
    workflow_stages: list[str] = Field(default_factory=list)
    public_spec_anchors: list[str] = Field(default_factory=list)
    proof_summary: str = ""
    redaction_profile_version: str = "1.0"
    source_kind: str = "resolution"
    integrity_hash: str = ""
    emitted_at: str = ""
