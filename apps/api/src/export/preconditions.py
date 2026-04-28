"""Export precondition checks — INV-004 enforcement.

High-impact resolutions CANNOT be exported without a human_decision
node with 'approve' in the evidence chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreconditionResult:
    """Result of export precondition check."""

    allowed: bool
    reason: str


def check_export_preconditions(
    evidence_chain_status: str,
    evidence_nodes: list[dict[str, Any]],
    is_high_impact: bool,
) -> PreconditionResult:
    """Check if an export is allowed.

    Preconditions (from contracts.md):
    1. Evidence chain must be in 'complete' status
    2. If high-impact, a human_decision node with 'approve' must exist (INV-004)

    Args:
        evidence_chain_status: Current chain status.
        evidence_nodes: List of evidence node dicts.
        is_high_impact: Whether the resolution is high-impact.

    Returns:
        PreconditionResult indicating if export is allowed.
    """
    if evidence_chain_status != "complete":
        return PreconditionResult(
            allowed=False,
            reason="Evidence chain is not complete",
        )

    if is_high_impact:
        has_approval = any(
            n.get("node_type") == "human_decision"
            and n.get("data", {}).get("decision") == "approve"
            for n in evidence_nodes
        )
        if not has_approval:
            return PreconditionResult(
                allowed=False,
                reason="High-impact resolution requires human approval before export (INV-004)",
            )

    return PreconditionResult(allowed=True, reason="")
