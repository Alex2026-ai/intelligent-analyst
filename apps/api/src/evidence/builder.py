"""Evidence Chain Builder — creates and extends evidence chains.

Append-only, immutable returns. Every operation returns a new chain object.
The builder never mutates an existing chain (INV-002).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode, NodeType

from apps.api.src.evidence.exceptions import ChainClosedError
from apps.api.src.evidence.hasher import hash_chain, hash_node_content


class EvidenceChainBuilder:
    """Manages the lifecycle of an evidence chain.

    All methods return new chain objects — the builder is stateless
    and never mutates input chains.
    """

    def create_chain(self, resolution_id: str, tenant_id: str) -> EvidenceChain:
        """Create a new evidence chain with no nodes.

        Args:
            resolution_id: UUID of the resolution this chain belongs to.
            tenant_id: Tenant ID (extracted from token, INV-005).

        Returns:
            New EvidenceChain in 'building' status with empty node list.
        """
        now = datetime.now(timezone.utc).isoformat()
        # Empty chain hash — will be computed when nodes are added
        empty_hash = hash_chain([])
        return EvidenceChain(
            chain_id=str(uuid.uuid4()),
            resolution_id=resolution_id,
            tenant_id=tenant_id,
            status=ChainStatus.BUILDING,
            chain_hash=empty_hash,
            nodes=[],
            created_at=now,
            updated_at=now,
        )

    def add_node(
        self,
        chain: EvidenceChain,
        node_type: NodeType,
        data: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> EvidenceChain:
        """Append a node to the chain.

        Computes the node hash, assigns sequence number, and recomputes
        the chain hash. Returns a new chain — original is unchanged.

        Args:
            chain: Existing evidence chain.
            node_type: Type of evidence node to add.
            data: Node-specific payload data.
            timestamp: Optional fixed timestamp (for deterministic testing).

        Returns:
            New EvidenceChain with the node appended.

        Raises:
            ChainClosedError: If the chain status is 'complete'.
        """
        if chain.status == ChainStatus.COMPLETE:
            raise ChainClosedError(chain.chain_id)

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        sequence = len(chain.nodes) + 1  # 1-indexed

        node_hash = hash_node_content(
            node_type=node_type.value,
            sequence=sequence,
            timestamp=ts,
            data=data,
        )

        new_node = EvidenceNode(
            node_id=str(uuid.uuid4()),
            node_type=node_type,
            sequence=sequence,
            timestamp=ts,
            node_hash=node_hash,
            data=data,
        )

        new_nodes = list(chain.nodes) + [new_node]
        new_chain_hash = hash_chain(new_nodes)

        return EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=ChainStatus.BUILDING,
            chain_hash=new_chain_hash,
            nodes=new_nodes,
            created_at=chain.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def close_chain(self, chain: EvidenceChain) -> EvidenceChain:
        """Mark chain as complete. Final chain hash is computed.

        Args:
            chain: Evidence chain to close.

        Returns:
            New EvidenceChain with status 'complete' and final chain hash.
        """
        final_hash = hash_chain(chain.nodes)

        return EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=ChainStatus.COMPLETE,
            chain_hash=final_hash,
            nodes=list(chain.nodes),
            created_at=chain.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
