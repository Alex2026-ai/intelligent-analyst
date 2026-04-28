"""Structured PMC audit events — deterministic, no private payloads.

Candidate events:    attempted, created, denied, failed
Publication events:  approve, publish, revoke (attempted/succeeded/failed)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ia.pmc.events")


def _safe_event(event_type: str, **fields: Any) -> dict[str, Any]:
    """Build a structured event dict. Never includes raw private payloads."""
    return {"event": event_type, **fields}


def emit_attempted(
    tenant_id: str, resolution_id: str, correlation_id: str = ""
) -> dict[str, Any]:
    """Emitted when PMC candidate creation is attempted."""
    event = _safe_event(
        "pmc_candidate_attempted",
        tenant_id=tenant_id,
        resolution_id=resolution_id,
        correlation_id=correlation_id,
    )
    logger.info("%s", event)
    return event


def emit_created(
    tenant_id: str,
    resolution_id: str,
    decision_id: str,
    decision_value: str,
    sample_id: str = "",
    correlation_id: str = "",
) -> dict[str, Any]:
    """Emitted when a PMC candidate is successfully created (pending or emitted)."""
    event = _safe_event(
        "pmc_candidate_created",
        tenant_id=tenant_id,
        resolution_id=resolution_id,
        decision_id=decision_id,
        decision=decision_value,
        sample_id=sample_id,
        correlation_id=correlation_id,
    )
    logger.info("%s", event)
    return event


def emit_denied(
    tenant_id: str,
    resolution_id: str,
    decision_id: str,
    reasons: list[str],
    correlation_id: str = "",
) -> dict[str, Any]:
    """Emitted when PMC evaluation denies candidate creation."""
    event = _safe_event(
        "pmc_candidate_denied",
        tenant_id=tenant_id,
        resolution_id=resolution_id,
        decision_id=decision_id,
        reasons=reasons,
        correlation_id=correlation_id,
    )
    logger.info("%s", event)
    return event


def emit_failed(
    tenant_id: str,
    resolution_id: str,
    error: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Emitted when PMC lifecycle hook fails internally."""
    event = _safe_event(
        "pmc_candidate_failed",
        tenant_id=tenant_id,
        resolution_id=resolution_id,
        error=error,
        correlation_id=correlation_id,
    )
    logger.warning("%s", event)
    return event


# --- Publication lifecycle events ---

def emit_publication_event(
    action: str, outcome: str, sample_id: str, reason: str = ""
) -> dict[str, Any]:
    """Emit a structured publication lifecycle event.

    action: approve | publish | revoke
    outcome: attempted | succeeded | failed
    """
    event = _safe_event(
        f"pmc_{action}_{outcome}",
        sample_id=sample_id,
        reason=reason,
    )
    if outcome == "failed":
        logger.warning("%s", event)
    else:
        logger.info("%s", event)
    return event
