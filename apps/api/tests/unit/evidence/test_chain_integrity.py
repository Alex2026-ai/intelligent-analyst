"""End-to-end: build chain → tamper → detect.

Tests the full integrity pipeline from construction through verification.
"""

from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.api.src.evidence.hasher import verify_chain
from apps.api.src.evidence.validator import validate_chain


class TestFullIntegrityPipeline:
    def test_build_and_verify(self):
        """Build a multi-node chain and verify it passes."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        chain = builder.add_node(chain, NodeType.RETRIEVAL_RESULT, {"query": "test", "score": 0.9})
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "routing_decision"})
        chain = builder.close_chain(chain)

        assert verify_chain(chain) is True
        result = validate_chain(chain)
        assert result.valid is True

    def test_tamper_single_byte_detected(self):
        """Modifying a single byte in node data is detected."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        chain = builder.close_chain(chain)

        # Tamper: change one character in data
        original_data = dict(chain.nodes[0].data)
        original_data["ref"] = "doc.pde"  # Single byte change
        tampered_node = EvidenceNode(
            node_id=chain.nodes[0].node_id,
            node_type=chain.nodes[0].node_type,
            sequence=chain.nodes[0].sequence,
            timestamp=chain.nodes[0].timestamp,
            node_hash=chain.nodes[0].node_hash,
            data=original_data,
        )
        tampered_chain = EvidenceChain(
            chain_id=chain.chain_id,
            resolution_id=chain.resolution_id,
            tenant_id=chain.tenant_id,
            status=chain.status,
            chain_hash=chain.chain_hash,
            nodes=[tampered_node],
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )

        assert verify_chain(tampered_chain) is False
        result = validate_chain(tampered_chain)
        assert result.valid is False

    def test_l1_resolution_flow(self):
        """Full L1 resolution produces a valid evidence chain."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r-l1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {
            "document_type": "regulatory",
            "content_length": 100,
        })
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {
            "step": "l1_rule_match",
            "rule_id": "R-001",
            "matched": True,
        })
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {
            "step": "routing_decision",
            "route_to_review": False,
        })
        chain = builder.close_chain(chain)

        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True
        assert len(chain.nodes) == 3

    def test_l2_resolution_flow(self):
        """Full L2 resolution produces a valid evidence chain."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r-l2", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {
            "document_type": "compliance",
            "content_length": 200,
        })
        chain = builder.add_node(chain, NodeType.RETRIEVAL_RESULT, {
            "step": "l2_exact_match",
            "precedent_id": "P-001",
            "similarity": 1.0,
        })
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {
            "step": "routing_decision",
            "route_to_review": False,
        })
        chain = builder.close_chain(chain)

        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True
        assert len(chain.nodes) == 3

    def test_review_flow_chain_left_open(self):
        """Routed-to-review resolution leaves chain open for reviewer."""
        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r-review", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {
            "document_type": "financial",
        })
        chain = builder.add_node(chain, NodeType.TRANSFORMATION, {
            "step": "routing_decision",
            "route_to_review": True,
            "reason": "low_confidence",
        })

        assert chain.status == ChainStatus.BUILDING  # Not closed
        assert verify_chain(chain) is True  # Still valid hash chain
