"""Resolution Engine — orchestrates L1 → L2 → L3 → L4 progression.

The engine collects evidence from each attempted layer and applies
routing logic to decide final disposition (INV-002, INV-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ia_shared.models.evidence import EvidenceChain, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.resolver.base import EvidenceRecord, LayerResult, ResolverConfig
from apps.api.src.resolver.l1_rules import resolve_l1
from apps.api.src.resolver.l2_matching import resolve_l2
from apps.api.src.resolver.routing import RoutingDecision, evaluate_routing


@dataclass(frozen=True)
class EngineResult:
    """Final result from the resolution engine.

    Captures the resolution outcome, routing decision, and all evidence
    collected across layers (INV-002: complete evidence lineage).
    """

    resolution: Optional[str]
    """Resolution text, None if routed to review."""

    confidence: float
    """Final confidence score."""

    layer_used: Optional[int]
    """Layer that produced the resolution (1-4), None if unresolved."""

    status: str
    """'resolved' or 'routed_to_review'."""

    review_reason: Optional[str]
    """Reason for routing to review, None if resolved."""

    evidence: list[EvidenceRecord] = field(default_factory=list)
    """All evidence records collected during resolution."""

    evidence_chain: Optional[EvidenceChain] = None
    """Full PRE evidence chain, populated when resolve_with_evidence is used."""


def resolve(
    content: str,
    document_type: str,
    metadata: dict[str, Any],
    config: ResolverConfig,
    rule_set: list[dict[str, Any]],
    precedents: list[dict[str, Any]],
    llm_available: bool = True,
) -> EngineResult:
    """Run the full resolution pipeline.

    Progresses through layers L1 → L2 → (L3 → L4 in future phases).
    Respects max_layer from config. Applies routing logic at the end.

    Args:
        content: Document content text.
        document_type: Document type classification string.
        metadata: Document metadata dict.
        config: Resolver configuration with all thresholds.
        rule_set: L1 rule set (list of rule dicts).
        precedents: L2 precedent store (list of precedent dicts).
        llm_available: Whether LLM providers are currently available.

    Returns:
        EngineResult with resolution, confidence, evidence, and routing decision.
    """
    all_evidence: list[EvidenceRecord] = []
    force_review = metadata.get("force_review", False)

    # Record input as source artifact (INV-002)
    all_evidence.append(
        EvidenceRecord(
            node_type="source_artifact",
            data={
                "document_type": document_type,
                "content_length": len(content),
                "has_force_review": force_review,
            },
        )
    )

    result: Optional[LayerResult] = None

    # --- L1: Deterministic rules ---
    if config.max_layer >= 1:
        l1_result = resolve_l1(
            content=content,
            document_type=document_type,
            metadata=metadata,
            rule_set=rule_set,
            rule_set_version=config.rule_set_version,
        )
        if l1_result:
            all_evidence.extend(l1_result.evidence)
            result = l1_result

    # --- L2: Matching ---
    if result is None and config.max_layer >= 2:
        l2_result = resolve_l2(
            content=content,
            document_type=document_type,
            metadata=metadata,
            precedents=precedents,
            config=config,
        )
        if l2_result:
            all_evidence.extend(l2_result.evidence)
            result = l2_result

    # --- L3/L4: Stubs for future phases ---
    # L3 and L4 return None — engine skips them.
    # These will be implemented in Phase 4.

    # --- Routing decision ---
    if result is not None:
        routing = evaluate_routing(
            confidence=result.confidence,
            document_type=document_type,
            force_review=force_review,
            llm_available=llm_available,
            config=config,
        )
        all_evidence.append(routing.evidence)

        if routing.route_to_review:
            return EngineResult(
                resolution=result.resolution,
                confidence=result.confidence,
                layer_used=result.layer_used,
                status="routed_to_review",
                review_reason=routing.reason,
                evidence=all_evidence,
            )

        return EngineResult(
            resolution=result.resolution,
            confidence=result.confidence,
            layer_used=result.layer_used,
            status="resolved",
            review_reason=None,
            evidence=all_evidence,
        )

    # No layer resolved — route to review (INV-003: fail-closed)
    routing = evaluate_routing(
        confidence=0.0,
        document_type=document_type,
        force_review=force_review,
        llm_available=llm_available,
        config=config,
    )
    all_evidence.append(routing.evidence)

    return EngineResult(
        resolution=None,
        confidence=0.0,
        layer_used=None,
        status="routed_to_review",
        review_reason=routing.reason or "low_confidence",
        evidence=all_evidence,
    )


def resolve_with_evidence(
    content: str,
    document_type: str,
    metadata: dict[str, Any],
    config: ResolverConfig,
    rule_set: list[dict[str, Any]],
    precedents: list[dict[str, Any]],
    resolution_id: str,
    tenant_id: str,
    llm_available: bool = True,
) -> EngineResult:
    """Run resolution pipeline and build a proper PRE evidence chain.

    Wraps resolve() and converts EvidenceRecords into a hash-protected
    EvidenceChain using the EvidenceChainBuilder (INV-002).

    Args:
        content: Document content text.
        document_type: Document type classification.
        metadata: Document metadata.
        config: Resolver configuration.
        rule_set: L1 rule set.
        precedents: L2 precedent store.
        resolution_id: UUID for the resolution record.
        tenant_id: Tenant ID (from auth token).
        llm_available: Whether LLM providers are available.

    Returns:
        EngineResult with evidence_chain populated.
    """
    # Run base resolution
    result = resolve(
        content=content,
        document_type=document_type,
        metadata=metadata,
        config=config,
        rule_set=rule_set,
        precedents=precedents,
        llm_available=llm_available,
    )

    # Build evidence chain from collected EvidenceRecords
    builder = EvidenceChainBuilder()
    chain = builder.create_chain(resolution_id=resolution_id, tenant_id=tenant_id)

    node_type_map = {
        "source_artifact": NodeType.SOURCE_ARTIFACT,
        "retrieval_result": NodeType.RETRIEVAL_RESULT,
        "transformation": NodeType.TRANSFORMATION,
        "model_call": NodeType.MODEL_CALL,
        "human_decision": NodeType.HUMAN_DECISION,
        "export_artifact": NodeType.EXPORT_ARTIFACT,
        "degradation_event": NodeType.DEGRADATION_EVENT,
    }

    for record in result.evidence:
        nt = node_type_map.get(record.node_type)
        if nt is not None:
            chain = builder.add_node(chain, nt, record.data)

    # Close chain if resolved, leave open if routed to review
    if result.status == "resolved":
        chain = builder.close_chain(chain)

    return EngineResult(
        resolution=result.resolution,
        confidence=result.confidence,
        layer_used=result.layer_used,
        status=result.status,
        review_reason=result.review_reason,
        evidence=result.evidence,
        evidence_chain=chain,
    )
