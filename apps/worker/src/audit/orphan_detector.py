"""Orphan detector — finds evidence chains without resolutions and vice versa.

Operates on in-memory data. Caller provides the sets of IDs.
INV-002: every resolution must have a corresponding evidence chain.
"""

from __future__ import annotations

from apps.api.src.evidence.types import OrphanReport


def detect_orphans(
    chain_resolution_ids: dict[str, str],
    resolution_ids: set[str],
) -> OrphanReport:
    """Detect orphaned chains and resolutions.

    Args:
        chain_resolution_ids: Mapping of chain_id → resolution_id
            for all evidence chains.
        resolution_ids: Set of all known resolution IDs.

    Returns:
        OrphanReport listing chains without resolutions and
        resolutions without chains.
    """
    chain_ids_by_resolution: dict[str, str] = {}
    chains_without_resolutions: list[str] = []

    for chain_id, resolution_id in chain_resolution_ids.items():
        if resolution_id not in resolution_ids:
            chains_without_resolutions.append(chain_id)
        else:
            chain_ids_by_resolution[resolution_id] = chain_id

    resolutions_without_chains = [
        rid for rid in resolution_ids if rid not in chain_ids_by_resolution
    ]

    return OrphanReport(
        chains_without_resolutions=sorted(chains_without_resolutions),
        resolutions_without_chains=sorted(resolutions_without_chains),
    )
