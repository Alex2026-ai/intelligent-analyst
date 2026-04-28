"""Tests for background integrity checker."""

from ia_shared.models.evidence import ChainStatus, EvidenceChain, EvidenceNode, NodeType

from apps.api.src.evidence.builder import EvidenceChainBuilder
from apps.worker.src.audit.integrity_checker import check_chains, chains_needing_warning


def _build_valid_chain(resolution_id: str = "r1") -> EvidenceChain:
    builder = EvidenceChainBuilder()
    chain = builder.create_chain(resolution_id, "t1")
    chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
    chain = builder.add_node(chain, NodeType.TRANSFORMATION, {"type": "routing"})
    return builder.close_chain(chain)


def _build_tampered_chain() -> EvidenceChain:
    chain = _build_valid_chain("r-tampered")
    tampered_node = EvidenceNode(
        node_id=chain.nodes[0].node_id,
        node_type=chain.nodes[0].node_type,
        sequence=chain.nodes[0].sequence,
        timestamp=chain.nodes[0].timestamp,
        node_hash=chain.nodes[0].node_hash,
        data={"ref": "TAMPERED.pdf"},
    )
    return EvidenceChain(
        chain_id=chain.chain_id,
        resolution_id=chain.resolution_id,
        tenant_id=chain.tenant_id,
        status=chain.status,
        chain_hash=chain.chain_hash,
        nodes=[tampered_node, chain.nodes[1]],
        created_at=chain.created_at,
        updated_at=chain.updated_at,
    )


class TestCheckChains:
    def test_all_valid(self):
        chains = [_build_valid_chain(f"r{i}") for i in range(5)]
        report = check_chains(chains)
        assert report.all_passed is True
        assert report.total_checked == 5
        assert report.passed == 5
        assert report.failed == 0

    def test_detects_tampered(self):
        chains = [_build_valid_chain("r1"), _build_tampered_chain()]
        report = check_chains(chains)
        assert report.all_passed is False
        assert report.passed == 1
        assert report.failed == 1
        assert len(report.violations) == 1

    def test_empty_batch(self):
        report = check_chains([])
        assert report.all_passed is True
        assert report.total_checked == 0


class TestChainsNeedingWarning:
    def test_flags_tampered_not_already_warned(self):
        tampered = _build_tampered_chain()
        results = chains_needing_warning([tampered])
        assert len(results) == 1
        assert results[0][0] == tampered.chain_id

    def test_skips_already_warned(self):
        tampered = _build_tampered_chain()
        # Mark as already warned
        warned = EvidenceChain(
            chain_id=tampered.chain_id,
            resolution_id=tampered.resolution_id,
            tenant_id=tampered.tenant_id,
            status=ChainStatus.INTEGRITY_WARNING,
            chain_hash=tampered.chain_hash,
            nodes=list(tampered.nodes),
            created_at=tampered.created_at,
            updated_at=tampered.updated_at,
        )
        results = chains_needing_warning([warned])
        assert len(results) == 0

    def test_valid_chains_not_flagged(self):
        results = chains_needing_warning([_build_valid_chain()])
        assert len(results) == 0
