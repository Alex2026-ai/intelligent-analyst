"""Tests for evidence chain repository — persistence, hash verification, subcollections."""

import pytest

from ia_shared.models.evidence import ChainStatus, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.evidence.hasher import verify_chain
from apps.api.src.storage.exceptions import DocumentNotFoundError, StorageError
from apps.api.src.storage.firestore.evidence_repo import EvidenceRepository


def _build_chain(node_count: int = 3) -> "EvidenceChain":
    builder = EvidenceChainBuilder()
    chain = builder.create_chain("r1", "t1")
    for i in range(node_count):
        chain = builder.add_node(
            chain, NodeType.TRANSFORMATION, {"step": f"step-{i}"}
        )
    return builder.close_chain(chain)


class TestSaveAndRetrieve:
    @pytest.mark.asyncio
    async def test_save_and_get(self, db):
        repo = EvidenceRepository(db, "t1")
        chain = _build_chain()
        await repo.save_chain(chain)
        retrieved = await repo.get_chain(chain.chain_id)
        assert retrieved.chain_id == chain.chain_id
        assert retrieved.status == ChainStatus.COMPLETE
        assert len(retrieved.nodes) == 3
        assert verify_chain(retrieved) is True

    @pytest.mark.asyncio
    async def test_get_not_found(self, db):
        repo = EvidenceRepository(db, "t1")
        with pytest.raises(DocumentNotFoundError):
            await repo.get_chain("nonexistent")

    @pytest.mark.asyncio
    async def test_get_by_resolution(self, db):
        repo = EvidenceRepository(db, "t1")
        chain = _build_chain()
        await repo.save_chain(chain)
        result = await repo.get_chain_by_resolution("r1")
        assert result is not None
        assert result.chain_id == chain.chain_id

    @pytest.mark.asyncio
    async def test_hash_verification_on_read(self, db):
        """Hash is verified on every read — fail-closed."""
        repo = EvidenceRepository(db, "t1")
        chain = _build_chain()
        await repo.save_chain(chain)
        # Tamper with stored chain hash
        key = f"tenants/t1/evidence_chains/{chain.chain_id}"
        db._data[key]["chain_hash"] = "tampered"
        with pytest.raises(StorageError, match="integrity check failed"):
            await repo.get_chain(chain.chain_id)


class TestSubcollectionPattern:
    @pytest.mark.asyncio
    async def test_large_chain_uses_subcollection(self, db):
        """Chains with >50 nodes use subcollection pattern."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r-big", "t1")
        for i in range(60):
            chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"i": i})
        chain = builder.close_chain(chain)

        repo = EvidenceRepository(db, "t1")
        await repo.save_chain(chain)

        # Verify inline nodes are empty
        key = f"tenants/t1/evidence_chains/{chain.chain_id}"
        assert db._data[key]["nodes"] == []

        # Verify subcollection nodes exist
        retrieved = await repo.get_chain(chain.chain_id)
        assert len(retrieved.nodes) == 60
        assert verify_chain(retrieved) is True

    @pytest.mark.asyncio
    async def test_small_chain_inline(self, db):
        repo = EvidenceRepository(db, "t1")
        chain = _build_chain(5)
        await repo.save_chain(chain)
        key = f"tenants/t1/evidence_chains/{chain.chain_id}"
        assert len(db._data[key]["nodes"]) == 5


class TestListChainIds:
    @pytest.mark.asyncio
    async def test_list_chain_ids(self, db):
        repo = EvidenceRepository(db, "t1")
        c1 = _build_chain()
        await repo.save_chain(c1)
        mapping = await repo.list_chain_ids()
        assert c1.chain_id in mapping
        assert mapping[c1.chain_id] == "r1"
