"""Node factory — creates typed evidence nodes.

Every NodeType in the registry has a dedicated factory method.
Each method produces an EvidenceNode with properly structured data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ia_shared.models.evidence import EvidenceNode, NodeType

from apps.api.src.evidence.hasher import hash_node_content


def _make_node(node_type: NodeType, sequence: int, data: dict[str, Any]) -> EvidenceNode:
    """Internal helper to create a hashed evidence node."""
    timestamp = datetime.now(timezone.utc).isoformat()
    node_hash = hash_node_content(
        node_type=node_type.value,
        sequence=sequence,
        timestamp=timestamp,
        data=data,
    )
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        node_type=node_type,
        sequence=sequence,
        timestamp=timestamp,
        node_hash=node_hash,
        data=data,
    )


def _make_node_at(
    node_type: NodeType, sequence: int, timestamp: str, data: dict[str, Any]
) -> EvidenceNode:
    """Create a node with a specific timestamp (for deterministic testing)."""
    node_hash = hash_node_content(
        node_type=node_type.value,
        sequence=sequence,
        timestamp=timestamp,
        data=data,
    )
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        node_type=node_type,
        sequence=sequence,
        timestamp=timestamp,
        node_hash=node_hash,
        data=data,
    )


class NodeFactory:
    """Factory for creating typed evidence nodes.

    Each method corresponds to a NodeType in the registry.
    All produced nodes have their SHA-256 hash pre-computed.
    """

    @staticmethod
    def source_artifact(
        sequence: int,
        artifact_ref: str,
        metadata: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """Document uploaded by analyst."""
        data = {"artifact_ref": artifact_ref, "metadata": metadata}
        if timestamp:
            return _make_node_at(NodeType.SOURCE_ARTIFACT, sequence, timestamp, data)
        return _make_node(NodeType.SOURCE_ARTIFACT, sequence, data)

    @staticmethod
    def retrieval_result(
        sequence: int,
        query: str,
        results: list[dict[str, Any]],
        match_score: float,
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """L2 matching results."""
        data = {"query": query, "results": results, "match_score": match_score}
        if timestamp:
            return _make_node_at(NodeType.RETRIEVAL_RESULT, sequence, timestamp, data)
        return _make_node(NodeType.RETRIEVAL_RESULT, sequence, data)

    @staticmethod
    def transformation(
        sequence: int,
        input_hash: str,
        output_hash: str,
        transform_type: str,
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """PII masking, routing decision, or other data transformation."""
        data = {
            "input_hash": input_hash,
            "output_hash": output_hash,
            "transform_type": transform_type,
        }
        if timestamp:
            return _make_node_at(NodeType.TRANSFORMATION, sequence, timestamp, data)
        return _make_node(NodeType.TRANSFORMATION, sequence, data)

    @staticmethod
    def model_call(
        sequence: int,
        prompt_version: str,
        provider: str,
        model: str,
        confidence: float,
        latency_ms: int,
        response_summary: str,
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """L3/L4 LLM call record."""
        data = {
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "response_summary": response_summary,
        }
        if timestamp:
            return _make_node_at(NodeType.MODEL_CALL, sequence, timestamp, data)
        return _make_node(NodeType.MODEL_CALL, sequence, data)

    @staticmethod
    def human_decision(
        sequence: int,
        decision: str,
        reviewer_id: str,
        notes: str,
        evidence_reviewed: list[str],
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """Reviewer's decision on a review case."""
        data = {
            "decision": decision,
            "reviewer_id": reviewer_id,
            "notes": notes,
            "evidence_reviewed": evidence_reviewed,
        }
        if timestamp:
            return _make_node_at(NodeType.HUMAN_DECISION, sequence, timestamp, data)
        return _make_node(NodeType.HUMAN_DECISION, sequence, data)

    @staticmethod
    def export_artifact(
        sequence: int,
        artifact_ref: str,
        format: str,
        hash: str,
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """Generated export artifact."""
        data = {"artifact_ref": artifact_ref, "format": format, "hash": hash}
        if timestamp:
            return _make_node_at(NodeType.EXPORT_ARTIFACT, sequence, timestamp, data)
        return _make_node(NodeType.EXPORT_ARTIFACT, sequence, data)

    @staticmethod
    def degradation_event(
        sequence: int,
        mode: str,
        reason: str,
        *,
        timestamp: str | None = None,
    ) -> EvidenceNode:
        """System degradation affecting this resolution."""
        data = {"mode": mode, "reason": reason}
        if timestamp:
            return _make_node_at(NodeType.DEGRADATION_EVENT, sequence, timestamp, data)
        return _make_node(NodeType.DEGRADATION_EVENT, sequence, data)
