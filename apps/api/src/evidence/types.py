"""Evidence types — re-exports from shared models plus builder-specific types."""

from __future__ import annotations

from dataclasses import dataclass, field

# Re-export shared types for convenience
from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode, NodeType  # noqa: F401


@dataclass(frozen=True)
class ValidationResult:
    """Result of evidence chain integrity validation."""

    valid: bool
    """Whether the chain passed all integrity checks."""

    chain_id: str
    """ID of the validated chain."""

    node_errors: list[NodeError] = field(default_factory=list)
    """Per-node validation errors, if any."""

    chain_hash_valid: bool = True
    """Whether the chain-level hash is correct."""

    expected_chain_hash: str = ""
    actual_chain_hash: str = ""


@dataclass(frozen=True)
class NodeError:
    """A single node integrity error."""

    node_id: str
    sequence: int
    expected_hash: str
    actual_hash: str
    message: str


@dataclass(frozen=True)
class OrphanReport:
    """Report of orphaned chains or resolutions."""

    chains_without_resolutions: list[str] = field(default_factory=list)
    """Chain IDs that have no corresponding resolution."""

    resolutions_without_chains: list[str] = field(default_factory=list)
    """Resolution IDs that have no corresponding evidence chain."""
