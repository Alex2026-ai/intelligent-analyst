"""Tests for resolver-evidence integration — resolver produces correct evidence chains."""

from ia_shared.models.evidence import ChainStatus, NodeType

from apps.api.src.evidence.hasher import verify_chain
from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.engine import resolve_with_evidence
from apps.api.tests.unit.resolver.conftest import SAMPLE_PRECEDENTS, SAMPLE_RULE_SET


class TestResolverEvidenceL1:
    def test_l1_produces_evidence_chain(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-test-l1",
            tenant_id="t-test",
        )
        assert result.evidence_chain is not None
        chain = result.evidence_chain
        assert chain.resolution_id == "r-test-l1"
        assert chain.tenant_id == "t-test"
        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True

    def test_l1_chain_has_correct_nodes(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r1",
            tenant_id="t1",
        )
        chain = result.evidence_chain
        node_types = [n.node_type for n in chain.nodes]
        assert NodeType.SOURCE_ARTIFACT in node_types
        assert NodeType.TRANSFORMATION in node_types  # rule match + routing


class TestResolverEvidenceL2:
    def test_l2_produces_evidence_chain(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-test-l2",
            tenant_id="t-test",
        )
        assert result.evidence_chain is not None
        chain = result.evidence_chain
        assert chain.status == ChainStatus.COMPLETE
        assert verify_chain(chain) is True

    def test_l2_chain_has_retrieval_result(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r1",
            tenant_id="t1",
        )
        chain = result.evidence_chain
        node_types = [n.node_type for n in chain.nodes]
        assert NodeType.RETRIEVAL_RESULT in node_types


class TestResolverEvidenceRouteToReview:
    def test_review_chain_left_open(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="Novel document with no matches.",
            document_type="medical",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-review",
            tenant_id="t1",
        )
        assert result.status == "routed_to_review"
        chain = result.evidence_chain
        assert chain.status == ChainStatus.BUILDING  # Not closed

    def test_force_review_chain_open(self):
        config = ResolverConfig()
        result = resolve_with_evidence(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={"force_review": True},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            resolution_id="r-force",
            tenant_id="t1",
        )
        assert result.status == "routed_to_review"
        chain = result.evidence_chain
        assert chain.status == ChainStatus.BUILDING
        assert verify_chain(chain) is True  # Hash still valid
