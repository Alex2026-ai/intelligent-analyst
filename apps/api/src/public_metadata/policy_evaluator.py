"""Deterministic policy evaluator — decides if a resolution may produce a public sample.

Fail-closed: missing policy, missing source data, unknown anchor, or redaction
uncertainty all result in DENY.
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
    PublicMetadataDecision,
    PublicMetadataPolicy,
)
from apps.api.src.public_metadata.redaction import redact_source

# Phase 1 public anchor allowlist
PHASE1_ANCHOR_ALLOWLIST: frozenset[str] = frozenset({"INV-002", "INV-005", "INV-006"})


def _compute_integrity_hash(data: dict[str, Any]) -> str:
    """Deterministic hash of decision data for integrity verification."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def filter_anchors(anchors: list[str], allowlist: frozenset[str]) -> list[str]:
    """Filter spec anchors to only those on the public allowlist (PMC-INV-005)."""
    return [a for a in anchors if a in allowlist]


def evaluate(
    source: dict[str, Any],
    tenant_id: str,
    policy: PublicMetadataPolicy | None,
    source_anchors: list[str] | None = None,
) -> PublicMetadataDecision:
    """Evaluate whether a resolution story is eligible for public derivation.

    Fail-closed: returns DENY on any uncertainty.

    Args:
        source: Resolution story data (internal format).
        tenant_id: Tenant that owns the source.
        policy: The active PublicMetadataPolicy, or None.
        source_anchors: Spec anchors from the source evidence chain.

    Returns:
        PublicMetadataDecision with eligibility result.
    """
    now = datetime.now(timezone.utc).isoformat()
    decision_id = str(uuid.uuid4())
    source_resolution_id = source.get("resolution_id", "unknown")
    reasons: list[str] = []

    # --- Fail-closed: no policy ---
    if policy is None:
        return PublicMetadataDecision(
            decision_id=decision_id,
            source_resolution_id=source_resolution_id,
            tenant_id=tenant_id,
            policy_version="none",
            decision=Decision.DENY,
            reasons=["No PublicMetadataPolicy provided (PMC-INV-002)"],
            created_at=now,
            integrity_hash=_compute_integrity_hash({"deny": "no_policy"}),
        )

    # --- Fail-closed: deny_all mode ---
    if policy.mode.value == "deny_all":
        return PublicMetadataDecision(
            decision_id=decision_id,
            source_resolution_id=source_resolution_id,
            tenant_id=tenant_id,
            policy_version=policy.version,
            decision=Decision.DENY,
            reasons=["Policy mode is deny_all"],
            created_at=now,
            integrity_hash=_compute_integrity_hash({"deny": "deny_all"}),
        )

    # --- Blocked tenant ---
    if tenant_id in policy.blocked_tenants:
        return PublicMetadataDecision(
            decision_id=decision_id,
            source_resolution_id=source_resolution_id,
            tenant_id=tenant_id,
            policy_version=policy.version,
            decision=Decision.DENY,
            reasons=[f"Tenant '{tenant_id}' is blocked by policy"],
            created_at=now,
            integrity_hash=_compute_integrity_hash({"deny": "blocked_tenant"}),
        )

    # --- Fail-closed: missing source data ---
    if not source or not source.get("resolution_id"):
        return PublicMetadataDecision(
            decision_id=decision_id,
            source_resolution_id=source_resolution_id,
            tenant_id=tenant_id,
            policy_version=policy.version,
            decision=Decision.DENY,
            reasons=["Missing or empty source resolution data"],
            created_at=now,
            integrity_hash=_compute_integrity_hash({"deny": "missing_source"}),
        )

    # --- Unknown anchor check (PMC-INV-005) ---
    allowlist = frozenset(policy.public_anchor_allowlist)
    source_anchors = source_anchors or []
    unknown_anchors = [a for a in source_anchors if a not in allowlist]
    if unknown_anchors:
        reasons.append(f"Unknown anchors dropped: {unknown_anchors}")

    # --- Perform redaction ---
    _, dropped_fields, generalized_fields = redact_source(source)

    # --- Determine decision ---
    if policy.require_manual_approval:
        decision = Decision.REQUIRES_MANUAL_APPROVAL
        manual_required = True
        approval_status = ManualApprovalStatus.PENDING
        reasons.append("Manual approval required by policy (PMC-INV-007)")
    elif policy.allow_real_sanitized_samples:
        decision = Decision.ALLOW_WITH_REDACTION_PROFILE
        manual_required = False
        approval_status = ManualApprovalStatus.NOT_REQUIRED
        reasons.append("Auto-sanitized sample allowed by policy")
    else:
        decision = Decision.DENY
        manual_required = False
        approval_status = ManualApprovalStatus.NOT_REQUIRED
        reasons.append("Policy does not allow real sanitized samples and manual approval not enabled")

    integrity_data = {
        "decision": decision.value,
        "source_resolution_id": source_resolution_id,
        "tenant_id": tenant_id,
        "policy_version": policy.version,
        "dropped_fields": sorted(dropped_fields),
        "generalized_fields": sorted(generalized_fields),
    }

    return PublicMetadataDecision(
        decision_id=decision_id,
        source_resolution_id=source_resolution_id,
        tenant_id=tenant_id,
        policy_version=policy.version,
        decision=decision,
        manual_approval_required=manual_required,
        manual_approval_status=approval_status,
        dropped_fields=dropped_fields,
        generalized_fields=generalized_fields,
        reasons=reasons,
        created_at=now,
        integrity_hash=_compute_integrity_hash(integrity_data),
    )
