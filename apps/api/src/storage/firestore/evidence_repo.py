"""Evidence chain repository — tenant-scoped, append-only, hash-verified.

Stores chains in evidence_chains collection. Large chains (>50 nodes)
use subcollection pattern: evidence_chains/{id}/nodes/{node_id}.
Hash verification on every read (fail-closed).

Async-safe: all Firestore operations use _await_if_needed() and
_collect_stream() for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any, Optional

from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode

from apps.api.src.evidence.hasher import verify_chain
from apps.api.src.storage.exceptions import DocumentNotFoundError, StorageError
from apps.api.src.storage.firestore.base import BaseRepository

CHAINS_COLLECTION = "evidence_chains"
NODES_COLLECTION = "evidence_nodes"
SUBCOLLECTION_THRESHOLD = 50


class EvidenceRepository(BaseRepository):
    """Tenant-scoped evidence chain storage with hash verification."""

    async def save_chain(self, chain: EvidenceChain) -> None:
        """Save an evidence chain and its nodes.

        For chains with <= 50 nodes, nodes are stored inline.
        For larger chains, nodes go in a subcollection.
        """
        chain_data = self._with_schema_version({
            "chain_id": chain.chain_id,
            "resolution_id": chain.resolution_id,
            "status": chain.status.value if hasattr(chain.status, "value") else chain.status,
            "chain_hash": chain.chain_hash,
            "node_count": len(chain.nodes),
            "created_at": chain.created_at,
            "updated_at": chain.updated_at,
        })

        if len(chain.nodes) <= SUBCOLLECTION_THRESHOLD:
            # Inline nodes
            chain_data["nodes"] = [self._serialize_node(n) for n in chain.nodes]
        else:
            chain_data["nodes"] = []  # Nodes in subcollection

        await self._await_if_needed(
            self._collection(CHAINS_COLLECTION).document(chain.chain_id).set(chain_data)
        )

        # Store large chains in subcollection
        if len(chain.nodes) > SUBCOLLECTION_THRESHOLD:
            for node in chain.nodes:
                node_data = self._with_schema_version(self._serialize_node(node))
                node_data["chain_id"] = chain.chain_id
                await self._await_if_needed(
                    self._db.collection(
                        f"{self._base_path}/{CHAINS_COLLECTION}/{chain.chain_id}/nodes"
                    ).document(node.node_id).set(node_data)
                )

    async def get_chain(self, chain_id: str) -> EvidenceChain:
        """Get an evidence chain by ID with hash verification.

        Raises:
            DocumentNotFoundError: If chain doesn't exist.
            StorageError: If hash verification fails (integrity warning).
        """
        doc = self._collection(CHAINS_COLLECTION).document(chain_id).get()
        chain_data = await self._await_if_needed(doc)
        if chain_data is None:
            raise DocumentNotFoundError(CHAINS_COLLECTION, chain_id)

        # Handle DocumentSnapshot from real Firestore
        if hasattr(chain_data, "to_dict"):
            chain_data = chain_data.to_dict()
            if chain_data is None:
                raise DocumentNotFoundError(CHAINS_COLLECTION, chain_id)

        # Load nodes
        if chain_data.get("nodes"):
            nodes = [self._deserialize_node(n) for n in chain_data["nodes"]]
        else:
            # Load from subcollection
            stream = self._db.collection(
                f"{self._base_path}/{CHAINS_COLLECTION}/{chain_id}/nodes"
            ).stream()
            node_results = await self._collect_stream(stream)
            nodes = [self._deserialize_node(data) for _, data in node_results]
            nodes.sort(key=lambda n: n.sequence)

        chain = EvidenceChain(
            chain_id=chain_data["chain_id"],
            resolution_id=chain_data["resolution_id"],
            tenant_id=self._tenant_id,
            status=ChainStatus(chain_data["status"]),
            chain_hash=chain_data["chain_hash"],
            nodes=nodes,
            created_at=chain_data["created_at"],
            updated_at=chain_data["updated_at"],
        )

        # Hash verification on every read (fail-closed)
        if not verify_chain(chain):
            raise StorageError(
                f"Evidence chain integrity check failed for chain {chain_id}"
            )

        return chain

    async def get_chain_by_resolution(self, resolution_id: str) -> Optional[EvidenceChain]:
        """Find evidence chain by resolution_id."""
        stream = (
            self._collection(CHAINS_COLLECTION)
            .where("resolution_id", "==", resolution_id)
            .stream()
        )
        results = await self._collect_stream(stream)
        if not results:
            return None
        _, chain_data = results[0]
        return await self.get_chain(chain_data["chain_id"])

    async def list_chain_ids(self) -> dict[str, str]:
        """List all chain_id → resolution_id mappings for this tenant."""
        stream = self._collection(CHAINS_COLLECTION).stream()
        results = await self._collect_stream(stream)
        return {data["chain_id"]: data["resolution_id"] for _, data in results}

    @staticmethod
    def _serialize_node(node: EvidenceNode) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "node_type": node.node_type.value if hasattr(node.node_type, "value") else node.node_type,
            "sequence": node.sequence,
            "timestamp": node.timestamp,
            "node_hash": node.node_hash,
            "data": node.data,
        }

    @staticmethod
    def _deserialize_node(data: dict[str, Any]) -> EvidenceNode:
        from ia_shared.models.evidence import NodeType as NT
        node_type_val = data["node_type"]
        if isinstance(node_type_val, str):
            node_type_val = NT(node_type_val)
        return EvidenceNode(
            node_id=data["node_id"],
            node_type=node_type_val,
            sequence=data["sequence"],
            timestamp=data["timestamp"],
            node_hash=data["node_hash"],
            data=data.get("data", {}),
        )
