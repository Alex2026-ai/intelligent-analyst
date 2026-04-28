"""Background integrity checker for evidence chains.

Validates chains in batch. Reports violations but never auto-repairs
(FP-008: no unauthorized self-healing).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ia_shared.models.evidence import ChainStatus, EvidenceChain

from apps.api.src.evidence.validator import validate_chain
from apps.api.src.evidence.types import ValidationResult


@dataclass
class IntegrityReport:
    """Results of a batch integrity check run."""

    total_checked: int = 0
    passed: int = 0
    failed: int = 0
    violations: list[ValidationResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


def check_chains(chains: list[EvidenceChain]) -> IntegrityReport:
    """Validate a batch of evidence chains.

    Checks every node hash and chain hash. Chains that fail are
    recorded in the report with full details.

    Does NOT modify chains. Does NOT auto-repair. Flag only.

    Args:
        chains: List of evidence chains to validate.

    Returns:
        IntegrityReport with pass/fail counts and violation details.
    """
    report = IntegrityReport()

    for chain in chains:
        report.total_checked += 1
        result = validate_chain(chain)

        if result.valid:
            report.passed += 1
        else:
            report.failed += 1
            report.violations.append(result)

    return report


def chains_needing_warning(
    chains: list[EvidenceChain],
) -> list[tuple[str, ValidationResult]]:
    """Identify chains that should be flagged as integrity_warning.

    Returns chain_ids that fail validation but are not already flagged.
    Does NOT modify chains — caller decides what to do.

    Args:
        chains: List of evidence chains to check.

    Returns:
        List of (chain_id, validation_result) for chains needing warning.
    """
    results: list[tuple[str, ValidationResult]] = []

    for chain in chains:
        if chain.status == ChainStatus.INTEGRITY_WARNING:
            continue  # Already flagged
        result = validate_chain(chain)
        if not result.valid:
            results.append((chain.chain_id, result))

    return results
