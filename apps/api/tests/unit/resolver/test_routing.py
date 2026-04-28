"""Tests for review routing logic."""

from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.routing import evaluate_routing


class TestRoutingReasons:
    def test_force_review(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=1.0,
            document_type="regulatory",
            force_review=True,
            llm_available=True,
            config=config,
        )
        assert decision.route_to_review is True
        assert decision.reason == "force_review"

    def test_low_confidence(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.5,
            document_type="regulatory",
            force_review=False,
            llm_available=True,
            config=config,
        )
        assert decision.route_to_review is True
        assert decision.reason == "low_confidence"

    def test_llm_unavailable_with_low_confidence(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.5,
            document_type="regulatory",
            force_review=False,
            llm_available=False,
            config=config,
        )
        assert decision.route_to_review is True
        assert decision.reason == "llm_unavailable"

    def test_llm_unavailable_with_high_confidence_no_review(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.95,
            document_type="regulatory",
            force_review=False,
            llm_available=False,
            config=config,
        )
        assert decision.route_to_review is False
        assert decision.reason is None

    def test_high_confidence_no_review(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.95,
            document_type="regulatory",
            force_review=False,
            llm_available=True,
            config=config,
        )
        assert decision.route_to_review is False
        assert decision.reason is None

    def test_at_threshold_no_review(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.85,
            document_type="regulatory",
            force_review=False,
            llm_available=True,
            config=config,
        )
        assert decision.route_to_review is False


class TestRoutingPriority:
    def test_force_review_takes_priority_over_low_confidence(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.5,
            document_type="regulatory",
            force_review=True,
            llm_available=True,
            config=config,
        )
        assert decision.reason == "force_review"

    def test_force_review_takes_priority_over_llm_unavailable(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.5,
            document_type="regulatory",
            force_review=True,
            llm_available=False,
            config=config,
        )
        assert decision.reason == "force_review"


class TestRoutingEvidence:
    def test_evidence_always_produced(self):
        config = ResolverConfig(review_threshold=0.85)
        decision = evaluate_routing(
            confidence=0.95,
            document_type="regulatory",
            force_review=False,
            llm_available=True,
            config=config,
        )
        assert decision.evidence is not None
        assert decision.evidence.node_type == "transformation"
        assert decision.evidence.data["step"] == "routing_decision"

    def test_evidence_contains_threshold(self):
        config = ResolverConfig(review_threshold=0.75)
        decision = evaluate_routing(
            confidence=0.5,
            document_type="regulatory",
            force_review=False,
            llm_available=True,
            config=config,
        )
        assert decision.evidence.data["review_threshold"] == 0.75
        assert decision.evidence.data["confidence"] == 0.5
