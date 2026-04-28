"""Tests for EvidenceChainBuilder — create, append, close, immutability."""

import pytest

from ia_shared.models.evidence import ChainStatus, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.evidence.exceptions import ChainClosedError
from apps.api.src.evidence.hasher import verify_chain


class TestCreateChain:
    def test_creates_empty_chain(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        assert chain.resolution_id == "r1"
        assert chain.tenant_id == "t1"
        assert chain.status == ChainStatus.BUILDING
        assert len(chain.nodes) == 0

    def test_unique_chain_ids(self):
        builder = EvidenceChainBuilder()
        c1 = builder.create_chain("r1", "t1")
        c2 = builder.create_chain("r2", "t1")
        assert c1.chain_id != c2.chain_id


class TestAddNode:
    def test_append_node(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        assert len(chain.nodes) == 1
        assert chain.nodes[0].sequence == 1
        assert chain.nodes[0].node_type == NodeType.SOURCE_ARTIFACT

    def test_sequential_nodes(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "pii_mask"})
        chain = builder.add_node(chain, NodeType.RETRIEVAL_RESULT, {"query": "test"})
        assert len(chain.nodes) == 3
        assert [n.sequence for n in chain.nodes] == [1, 2, 3]

    def test_immutability(self):
        """Adding a node returns a new chain — original unchanged."""
        builder = EvidenceChainBuilder()
        original = builder.create_chain("r1", "t1")
        modified = builder.add_node(original, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        assert len(original.nodes) == 0
        assert len(modified.nodes) == 1

    def test_chain_hash_updates(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        h0 = chain.chain_hash
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "a"})
        h1 = chain.chain_hash
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "b"})
        h2 = chain.chain_hash
        assert h0 != h1
        assert h1 != h2

    def test_cannot_add_to_closed_chain(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        closed = builder.close_chain(chain)
        with pytest.raises(ChainClosedError):
            builder.add_node(closed, NodeType.TRANSFORMATION, {"type": "test"})


class TestCloseChain:
    def test_close_sets_complete(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        closed = builder.close_chain(chain)
        assert closed.status == ChainStatus.COMPLETE

    def test_close_immutability(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        closed = builder.close_chain(chain)
        assert chain.status == ChainStatus.BUILDING
        assert closed.status == ChainStatus.COMPLETE

    def test_closed_chain_verifies(self):
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "routing"})
        closed = builder.close_chain(chain)
        assert verify_chain(closed) is True


class TestAppendOnly:
    def test_no_modify_method_exists(self):
        """EvidenceChainBuilder has no method to modify or delete nodes."""
        builder = EvidenceChainBuilder()
        forbidden = ["modify_node", "delete_node", "remove_node", "update_node",
                      "replace_node", "insert_node"]
        for method in forbidden:
            assert not hasattr(builder, method), f"Forbidden method '{method}' exists!"

    def test_no_delete_method_exists(self):
        builder = EvidenceChainBuilder()
        assert not hasattr(builder, "delete_chain")
        assert not hasattr(builder, "remove_chain")
