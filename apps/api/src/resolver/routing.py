"""Review routing logic.

Decides whether a resolution needs human review (INV-003: fail-closed on ambiguity).
Routing decision is recorded in the evidence chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.api.src.resolver.base import EvidenceRecord, ResolverConfig


@dataclass(frozen=True)
class RoutingDecision:
    """Result of the routing evaluation.

    If route_to_review is True, the resolution is sent to the human review queue.
    """

    route_to_review: bool
    reason: Optional[str]
    evidence: EvidenceRecord


def evaluate_routing(
    confidence: float,
    document_type: str,
    force_review: bool,
    llm_available: bool,
    config: ResolverConfig,
) -> RoutingDecision:
    """Evaluate whether a resolution should be routed to human review.

    Checks are evaluated in priority order. The first matching reason wins.

    Args:
        confidence: Resolution confidence score (0.0-1.0).
        document_type: The document's type classification.
        force_review: Whether the submitter requested forced review.
        llm_available: Whether LLM providers are currently available.
        config: Resolver configuration with thresholds.

    Returns:
        RoutingDecision with reason and evidence record.
    """
    reason: Optional[str] = None

    if force_review:
        reason = "force_review"
    elif not llm_available and confidence < config.review_threshold:
        reason = "llm_unavailable"
    elif confidence < config.review_threshold:
        reason = "low_confidence"

    route = reason is not None

    evidence = EvidenceRecord(
        node_type="transformation",
        data={
            "step": "routing_decision",
            "route_to_review": route,
            "reason": reason,
            "confidence": confidence,
            "review_threshold": config.review_threshold,
            "force_review": force_review,
            "llm_available": llm_available,
        },
    )

    return RoutingDecision(
        route_to_review=route,
        reason=reason,
        evidence=evidence,
    )
