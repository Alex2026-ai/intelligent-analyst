"""Tests for resolution engine orchestration."""

from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.engine import resolve
from apps.api.tests.unit.resolver.conftest import SAMPLE_PRECEDENTS, SAMPLE_RULE_SET


class TestLayerProgression:
    def test_l1_resolves_stops_at_l1(self):
        config = ResolverConfig()
        result = resolve(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.layer_used == 1
        assert result.confidence == 1.0
        assert result.status == "resolved"

    def test_l1_miss_falls_through_to_l2(self):
        config = ResolverConfig()
        result = resolve(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.layer_used == 2
        assert result.confidence == 1.0
        assert result.status == "resolved"

    def test_no_match_routes_to_review(self):
        config = ResolverConfig()
        result = resolve(
            content="Completely novel document with no precedent.",
            document_type="financial",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.status == "routed_to_review"
        assert result.review_reason is not None
        assert result.layer_used is None


class TestMaxLayer:
    def test_max_layer_1_only_tries_l1(self):
        config = ResolverConfig(max_layer=1)
        # This would match L2 but max_layer=1 prevents it
        result = resolve(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.status == "routed_to_review"
        assert result.layer_used is None

    def test_max_layer_2_tries_l1_and_l2(self):
        config = ResolverConfig(max_layer=2)
        result = resolve(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.layer_used == 2
        assert result.status == "resolved"


class TestForceReview:
    def test_force_review_routes_even_with_high_confidence(self):
        config = ResolverConfig()
        result = resolve(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={"force_review": True},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.status == "routed_to_review"
        assert result.review_reason == "force_review"
        assert result.confidence == 1.0
        assert result.layer_used == 1

    def test_no_force_review_resolves(self):
        config = ResolverConfig()
        result = resolve(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={"force_review": False},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.status == "resolved"


class TestLowConfidenceRouting:
    def test_l2_below_review_threshold_routes(self):
        config = ResolverConfig(review_threshold=0.99, l2_match_threshold=0.3)
        result = resolve(
            content="SOX compliance audit FY2025 - controls checked",
            document_type="compliance",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        if result.layer_used == 2:
            # If L2 matched but confidence < 0.99, should route to review
            assert result.status == "routed_to_review"
            assert result.review_reason == "low_confidence"


class TestEvidenceCollection:
    def test_evidence_always_starts_with_source_artifact(self):
        config = ResolverConfig()
        result = resolve(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert len(result.evidence) >= 2
        assert result.evidence[0].node_type == "source_artifact"

    def test_evidence_contains_routing_decision(self):
        config = ResolverConfig()
        result = resolve(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        routing_evidence = [e for e in result.evidence if e.data.get("step") == "routing_decision"]
        assert len(routing_evidence) == 1

    def test_unresolved_has_evidence(self):
        config = ResolverConfig()
        result = resolve(
            content="Completely novel document.",
            document_type="medical",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert len(result.evidence) >= 2  # source_artifact + routing
        assert result.evidence[0].node_type == "source_artifact"


class TestLLMAvailability:
    def test_llm_unavailable_with_no_match_routes(self):
        config = ResolverConfig()
        result = resolve(
            content="Novel document.",
            document_type="medical",
            metadata={},
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
            llm_available=False,
        )
        assert result.status == "routed_to_review"
