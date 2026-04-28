"""Evidence chain integrity validator.

Validates node hashes, chain hash, and sequence ordering.
Never auto-repairs — flag and alert only (FP-008: no unauthorized self-healing).
"""

from __future__ import annotations

from ia_shared.models.evidence import EvidenceChain

from apps.api.src.evidence.hasher import hash_chain, hash_node
from apps.api.src.evidence.types import NodeError, ValidationResult


def validate_chain(chain: EvidenceChain) -> ValidationResult:
    """Validate the integrity of an evidence chain.

    Checks:
    1. Each node's hash matches recomputed hash
    2. Node sequences are contiguous (1, 2, 3, ...)
    3. Chain hash matches recomputed hash from ordered node hashes

    Args:
        chain: Evidence chain to validate.

    Returns:
        ValidationResult with details of any errors found.
    """
    node_errors: list[NodeError] = []

    # Check node hashes
    for node in chain.nodes:
        recomputed = hash_node(node)
        if recomputed != node.node_hash:
            node_errors.append(
                NodeError(
                    node_id=node.node_id,
                    sequence=node.sequence,
                    expected_hash=node.node_hash,
                    actual_hash=recomputed,
                    message=f"Node hash mismatch at sequence {node.sequence}",
                )
            )

    # Check sequence ordering
    expected_sequences = list(range(1, len(chain.nodes) + 1))
    actual_sequences = sorted(n.sequence for n in chain.nodes)
    if actual_sequences != expected_sequences:
        node_errors.append(
            NodeError(
                node_id="",
                sequence=0,
                expected_hash="",
                actual_hash="",
                message=(
                    f"Sequence gap: expected {expected_sequences}, "
                    f"got {actual_sequences}"
                ),
            )
        )

    # Check chain hash
    recomputed_chain_hash = hash_chain(chain.nodes)
    chain_hash_valid = recomputed_chain_hash == chain.chain_hash

    valid = len(node_errors) == 0 and chain_hash_valid

    return ValidationResult(
        valid=valid,
        chain_id=chain.chain_id,
        node_errors=node_errors,
        chain_hash_valid=chain_hash_valid,
        expected_chain_hash=chain.chain_hash,
        actual_chain_hash=recomputed_chain_hash,
    )
