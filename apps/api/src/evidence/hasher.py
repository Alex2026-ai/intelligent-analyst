"""SHA-256 hashing for evidence nodes and chains.

Serialization algorithm (contract):
1. Node hash: SHA-256 of canonical JSON of {node_type, sequence, timestamp, data}
2. Chain hash: SHA-256 of concatenated node hashes in sequence order
3. Canonical JSON: json.dumps with sort_keys=True, separators=(",", ":"), ensure_ascii=True

Hash algorithm: SHA-256 exclusively (INV-010).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ia_shared.models.evidence import EvidenceChain, EvidenceNode


def _canonical_json(obj: dict[str, Any]) -> str:
    """Produce deterministic JSON serialization.

    Uses sorted keys, compact separators, and ASCII encoding
    to guarantee identical output for identical data.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_node_content(
    node_type: str,
    sequence: int,
    timestamp: str,
    data: dict[str, Any],
) -> str:
    """Compute SHA-256 hash of node content.

    The hash covers node_type, sequence, timestamp, and data —
    the immutable content fields. node_id and node_hash are excluded
    (node_id is an identifier, node_hash is what we're computing).

    Args:
        node_type: Evidence node type string.
        sequence: Position in chain (1-indexed).
        timestamp: ISO 8601 timestamp string.
        data: Node-specific payload.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    content = {
        "node_type": node_type,
        "sequence": sequence,
        "timestamp": timestamp,
        "data": data,
    }
    canonical = _canonical_json(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_node(node: EvidenceNode) -> str:
    """Compute SHA-256 hash of an EvidenceNode's content."""
    return hash_node_content(
        node_type=node.node_type.value if hasattr(node.node_type, "value") else node.node_type,
        sequence=node.sequence,
        timestamp=node.timestamp,
        data=node.data,
    )


def hash_chain(nodes: list[EvidenceNode]) -> str:
    """Compute SHA-256 hash of ordered node hashes.

    The chain hash is the SHA-256 of all node hashes concatenated
    in sequence order. This detects reordering, insertion, and deletion.

    Args:
        nodes: List of evidence nodes in sequence order.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    sorted_nodes = sorted(nodes, key=lambda n: n.sequence)
    concatenated = "".join(n.node_hash for n in sorted_nodes)
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def verify_node(node: EvidenceNode) -> bool:
    """Recompute a node's hash and compare to stored hash.

    Returns:
        True if the stored hash matches the recomputed hash.
    """
    return hash_node(node) == node.node_hash


def verify_chain(chain: EvidenceChain) -> bool:
    """Verify all node hashes and the chain hash.

    Returns:
        True if all nodes verify and the chain hash is correct.
    """
    for node in chain.nodes:
        if not verify_node(node):
            return False
    return hash_chain(chain.nodes) == chain.chain_hash
