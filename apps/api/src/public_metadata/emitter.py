"""Sample emitter — produces PublicAuthoritySample from evaluated decisions.

No LLM summarization. Narrative assembled from deterministic templates only.
Fail-closed: will not emit if decision is not ALLOW or approved REQUIRES_MANUAL_APPROVAL.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from apps.api.src.public_metadata.models import (
    Decision,
    ManualApprovalStatus,
    OutcomeClass,
    PublicAuthoritySample,
    PublicMetadataDecision,
    PublicMetadataPolicy,
    SampleStatus,
)
from apps.api.src.public_metadata.policy_evaluator import evaluate, filter_anchors
from apps.api.src.public_metadata.redaction import OUTCOME_TEMPLATES, scrub_text


# ---------------------------------------------------------------------------
# Deterministic narrative templates
# ---------------------------------------------------------------------------

HEADLINE_TEMPLATES: dict[str, str] = {
    "resolved": "Automated resolution completed with verified confidence",
    "routed_to_review": "Policy discrepancy correctly routed for human review",
    "human_review_required": "System preserved escalation for expert assessment",
    "compliance_flag": "Compliance assessment completed per regulatory requirements",
    "risk_assessment": "Risk evaluation completed through multi-layer analysis",
}

WORKFLOW_STAGE_LABELS: list[str] = [
    "Document Intake",
    "PII Protection",
    "Deterministic Analysis",
    "Confidence Scoring",
    "Evidence Chain Construction",
    "Integrity Verification",
]


def _map_outcome_class(source: dict[str, Any]) -> OutcomeClass:
    """Map source status to a public outcome class."""
    status = source.get("status", "")
    if status == "resolved":
        return OutcomeClass.RESOLVED
    if status in ("routed_to_review", "pending"):
        return OutcomeClass.HUMAN_REVIEW_REQUIRED
    doc_type = source.get("document_type", "")
    if doc_type in ("regulatory", "compliance"):
        return OutcomeClass.COMPLIANCE_FLAG
    if doc_type == "financial":
        return OutcomeClass.RISK_ASSESSMENT
    return OutcomeClass.RESOLVED


def _build_headline(outcome: OutcomeClass) -> str:
    return HEADLINE_TEMPLATES.get(outcome.value, HEADLINE_TEMPLATES["resolved"])


def _build_summary(outcome: OutcomeClass) -> str:
    return OUTCOME_TEMPLATES.get(
        outcome.value,
        "The system completed analysis through its multi-layer resolution pipeline.",
    )


def _build_proof_summary(source_anchors: list[str], allowed: list[str]) -> str:
    """Build proof summary referencing only public-approved anchors."""
    if not allowed:
        return "Resolution verified through deterministic pipeline."
    parts = []
    if "INV-002" in allowed:
        parts.append("hash-protected evidence lineage")
    if "INV-005" in allowed:
        parts.append("tenant-isolated data scope")
    if "INV-006" in allowed:
        parts.append("PII-masked external processing")
    return f"Resolution verified through: {', '.join(parts)}."


def emit_sample(
    source: dict[str, Any],
    tenant_id: str,
    policy: PublicMetadataPolicy | None,
    decision: PublicMetadataDecision,
    source_anchors: list[str] | None = None,
) -> PublicAuthoritySample | None:
    """Produce a PublicAuthoritySample if the decision permits emission.

    Returns None if emission is not allowed. Fail-closed.

    Args:
        source: Internal resolution data.
        tenant_id: Owning tenant.
        policy: Active policy.
        decision: Evaluated decision from policy_evaluator.
        source_anchors: Spec anchors from evidence chain.

    Returns:
        PublicAuthoritySample or None if denied.
    """
    # Fail-closed gate
    if decision.decision == Decision.DENY:
        return None

    if decision.decision == Decision.REQUIRES_MANUAL_APPROVAL:
        if decision.manual_approval_status != ManualApprovalStatus.APPROVED:
            return None  # PMC-INV-007: blocked until approved

    # Filter anchors to allowlist (PMC-INV-005)
    allowed_anchors = filter_anchors(
        source_anchors or [],
        frozenset(policy.public_anchor_allowlist) if policy else frozenset(),
    )

    outcome = _map_outcome_class(source)
    headline = _build_headline(outcome)
    summary = _build_summary(outcome)
    proof = _build_proof_summary(source_anchors or [], allowed_anchors)

    now = datetime.now(timezone.utc).isoformat()
    sample_id = f"pub_{uuid.uuid4().hex[:12]}"

    # Build integrity hash over deterministic public content only
    # Excludes sample_id and decision_id (random UUIDs) to ensure
    # same input always yields same hash
    integrity_data = {
        "headline": headline,
        "summary": summary,
        "outcome_class": outcome.value,
        "anchors": sorted(allowed_anchors),
        "proof_summary": proof,
    }
    integrity_hash = hashlib.sha256(
        json.dumps(integrity_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return PublicAuthoritySample(
        public_sample_id=sample_id,
        status=SampleStatus.DRAFT,
        headline=headline,
        summary=summary,
        outcome_class=outcome,
        workflow_stages=WORKFLOW_STAGE_LABELS,
        public_spec_anchors=allowed_anchors,
        proof_summary=proof,
        integrity_hash=integrity_hash,
        emitted_at=now,
    )
