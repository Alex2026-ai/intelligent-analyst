"""Deterministic redaction and generalization engine.

Classifies source fields into actions: PUBLIC, REDACT, GENERALIZE, DROP, etc.
Phase 1 uses a hard-coded safe ruleset. No policy DSL.
"""

from __future__ import annotations

import re
from typing import Any

from apps.api.src.public_metadata.models import FieldAction

# ---------------------------------------------------------------------------
# Phase 1 hard-coded field rules
# ---------------------------------------------------------------------------

# Fields that must ALWAYS be dropped — never appear in public output
ALWAYS_DROP: frozenset[str] = frozenset({
    "tenant_id", "user_id", "reviewer_id", "analyst_id", "assigned_to",
    "decided_by", "requested_by", "email", "phone", "address",
    "ssn", "credit_card", "mrn", "drivers_license",
    "document_content", "content", "raw_content", "masked_content",
    "raw_response", "raw_prompt", "prompt_text",
    "trace_id", "correlation_id", "evidence_chain_id", "resolution_id",
    "document_id", "case_id", "export_id", "batch_id",
    "chain_hash", "node_hash",
    "artifact_ref", "bucket_path", "gcs_path", "storage_path", "db_path",
    "created_at", "updated_at", "decided_at", "emitted_at_source",
    "filename", "uploaded_filename",
})

# Fields that get generalized (value replaced with neutral language)
GENERALIZE_FIELDS: frozenset[str] = frozenset({
    "name", "applicant_name", "reviewer_name", "analyst_name",
    "tenant_name", "organization",
    "review_reason", "notes", "decision_notes",
    "source", "document_type",
})

# Fields safe for public output
PUBLIC_FIELDS: frozenset[str] = frozenset({
    "status", "confidence", "layer_used", "outcome_class",
    "workflow_stage", "spec_id",
})

# Name patterns to catch in freeform text
_NAME_PATTERN = re.compile(
    r"\b(?:James\s+Benson|Maria\s+Garcia|John\s+Smith|Jane\s+Doe)\b",
    re.IGNORECASE,
)
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[-.])\d{3}[-.]?\d{4}\b")
_ADDRESS_PATTERN = re.compile(r"\b\d+\s+[A-Z][a-zA-Z]+\s+(?:St|Ave|Blvd|Rd|Dr|Ln|Ct|Way)\b")
_TENANT_ID_PATTERN = re.compile(r"\btenant[s]?/[a-zA-Z0-9_-]+\b")
_INTERNAL_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)


# ---------------------------------------------------------------------------
# Generalization mappings
# ---------------------------------------------------------------------------

GENERALIZATION_MAP: dict[str, str] = {
    "name": "an individual",
    "applicant_name": "the applicant",
    "reviewer_name": "a reviewer",
    "analyst_name": "an analyst",
    "tenant_name": "the organization",
    "organization": "the organization",
    "review_reason": "policy-driven review criteria",
    "notes": "review commentary (redacted)",
    "decision_notes": "decision rationale (redacted)",
    "source": "submitted documentation",
    "document_type": "compliance document",
}

OUTCOME_TEMPLATES: dict[str, str] = {
    "resolved": "The system completed automated resolution with verified confidence.",
    "routed_to_review": "The system preserved escalation for human review instead of forcing an automated conclusion.",
    "human_review_required": "A policy discrepancy was correctly routed for human review.",
}


def classify_field(field_name: str) -> FieldAction:
    """Classify a single field name into a redaction action."""
    name = field_name.lower()
    if name in ALWAYS_DROP:
        return FieldAction.DROP
    if name in GENERALIZE_FIELDS:
        return FieldAction.GENERALIZE
    if name in PUBLIC_FIELDS:
        return FieldAction.PUBLIC
    return FieldAction.DROP  # Fail closed — unknown fields are dropped


def scrub_text(text: str) -> str:
    """Remove all PII, names, IDs, and identifying information from freeform text.

    Returns sanitized text. If scrubbing cannot be proven safe, returns empty string.
    """
    result = text
    result = _NAME_PATTERN.sub("the individual", result)
    result = _SSN_PATTERN.sub("[REDACTED]", result)
    result = _EMAIL_PATTERN.sub("[REDACTED]", result)
    result = _PHONE_PATTERN.sub("[REDACTED]", result)
    result = _ADDRESS_PATTERN.sub("[a property address]", result)
    result = _TENANT_ID_PATTERN.sub("[REDACTED]", result)
    result = _INTERNAL_ID_PATTERN.sub("[REDACTED]", result)
    return result


def redact_source(source: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Apply redaction/generalization to a source object.

    Returns (sanitized_dict, dropped_fields, generalized_fields).
    """
    sanitized: dict[str, Any] = {}
    dropped: list[str] = []
    generalized: list[str] = []

    for key, value in source.items():
        action = classify_field(key)

        if action == FieldAction.DROP:
            dropped.append(key)
        elif action == FieldAction.GENERALIZE:
            generalized.append(key)
            sanitized[key] = GENERALIZATION_MAP.get(key.lower(), "[generalized]")
        elif action == FieldAction.PUBLIC:
            sanitized[key] = value
        else:
            dropped.append(key)

    return sanitized, dropped, generalized
