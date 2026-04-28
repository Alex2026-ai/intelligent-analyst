"""Base types and configuration for the resolver framework.

LayerResult captures the output of each resolution layer.
ResolverConfig holds all configurable thresholds (INV-011: no silent thresholds).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class EvidenceRecord:
    """A single evidence record produced during resolution.

    Lightweight representation that the engine collects and later
    persists as EvidenceNode objects in the evidence chain (INV-002).
    """

    node_type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LayerResult:
    """Output of a single resolution layer.

    Immutable — once a layer produces a result, it cannot be modified.
    """

    resolution: str
    """The resolution text (determination)."""

    confidence: float
    """Confidence score (0.0-1.0)."""

    layer_used: int
    """Which layer produced this result (1-4)."""

    evidence: list[EvidenceRecord] = field(default_factory=list)
    """Evidence records produced by this layer."""


@dataclass(frozen=True)
class ResolverConfig:
    """Configuration for the resolution engine.

    All thresholds are explicit — nothing hardcoded (INV-011).
    Tenant-specific overrides populate these from TenantConfig.
    """

    review_threshold: float = 0.85
    """Below this confidence → route to human review."""

    high_impact_threshold: float = 0.95
    """Above this → classify as high-impact (requires human signoff for export)."""

    l2_match_threshold: float = 0.6
    """Minimum L2 match similarity to accept as a resolution."""

    max_layer: int = 4
    """Maximum layer the engine will attempt (1-4)."""

    rule_set_version: str = "1.0"
    """Version identifier for the active L1 rule set."""


class LayerResolver(Protocol):
    """Protocol for a resolution layer.

    Each layer is a pure function: given document content and metadata,
    it returns a LayerResult or None (no match).
    """

    def resolve(
        self,
        content: str,
        document_type: str,
        metadata: dict[str, Any],
    ) -> Optional[LayerResult]: ...
