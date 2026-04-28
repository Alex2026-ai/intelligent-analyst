"""Tests for evidence chain validator — valid chains pass, tampered fail."""

from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.evidence.hasher import hash_chain
from apps.api.src.evidence.validator import validate_chain


def _build_valid_chain() -> EvidenceChain:
    builder = EvidenceChainBuilder()
    chain = builder.create_chain("r1", "t1")
    chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
    chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "routing"})
    return builder.close_chain(chain)


class TestValidChain:
    def test_valid_chain_passes(self):
        chain = _build_valid_chain()
        result = validate_chain(chain)
        assert result.valid is True
        assert result.chain_hash_valid is True
        assert len(result.node_errors) == 0


class TestTamperedNodes:
    def test_modified_data_detected(self):
        chain = _build_valid_chain()
        # Tamper with node data
        tampered_node = EvidenceNode(
            node_id=chain.nodes[0].node_id,
            node_type=chain.nodes[0].node_type,
            sequence=chain.nodes[0].sequence,
            timestamp=chain.nodes[0].timestamp,
            node_hash=chain.nodes[0].node_hash,  # Original hash
            data={"ref": "TAMPERED.pdf"},  # Changed data
        )
        tampered_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash=chain.chain_hash,
            nodes=[tampered_node, chain.nodes[1]],
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )
        result = validate_chain(tampered_chain)
        assert result.valid is False
        assert len(result.node_errors) >= 1

    def test_modified_hash_detected(self):
        chain = _build_valid_chain()
        # Tamper with node hash
        tampered_node = EvidenceNode(
            node_id=chain.nodes[0].node_id,
            node_type=chain.nodes[0].node_type,
            sequence=chain.nodes[0].sequence,
            timestamp=chain.nodes[0].timestamp,
            node_hash="0000000000000000000000000000000000000000000000000000000000000000",
            data=chain.nodes[0].data,
        )
        tampered_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash=chain.chain_hash,
            nodes=[tampered_node, chain.nodes[1]],
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )
        result = validate_chain(tampered_chain)
        assert result.valid is False


class TestTamperedChain:
    def test_swapped_sequences_detected(self):
        chain = _build_valid_chain()
        # Swap the sequence numbers — node hashes will no longer verify
        # because sequence is part of the hashed content
        swapped_0 = EvidenceNode(
            node_id=chain.nodes[0].node_id,
            node_type=chain.nodes[0].node_type,
            sequence=2,  # Was 1
            timestamp=chain.nodes[0].timestamp,
            node_hash=chain.nodes[0].node_hash,  # Old hash (for seq=1)
            data=chain.nodes[0].data,
        )
        swapped_1 = EvidenceNode(
            node_id=chain.nodes[1].node_id,
            node_type=chain.nodes[1].node_type,
            sequence=1,  # Was 2
            timestamp=chain.nodes[1].timestamp,
            node_hash=chain.nodes[1].node_hash,  # Old hash (for seq=2)
            data=chain.nodes[1].data,
        )
        reordered_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash=chain.chain_hash,
            nodes=[swapped_0, swapped_1],
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )
        result = validate_chain(reordered_chain)
        assert result.valid is False
        assert len(result.node_errors) >= 1

    def test_removed_node_detected(self):
        chain = _build_valid_chain()
        # Remove a node
        shortened_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash=chain.chain_hash,
            nodes=[chain.nodes[0]],  # Removed second node
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )
        result = validate_chain(shortened_chain)
        assert result.valid is False
        assert result.chain_hash_valid is False

    def test_tampered_chain_hash_detected(self):
        chain = _build_valid_chain()
        tampered_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash="aaaa" + chain.chain_hash[4:],  # Tampered hash
            nodes=list(chain.nodes),
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )
        result = validate_chain(tampered_chain)
        assert result.valid is False
        assert result.chain_hash_valid is False
