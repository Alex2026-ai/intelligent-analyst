"""Tests for confidence scoring module."""

from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.confidence import (
    is_above_l2_match_threshold,
    is_below_review_threshold,
    l1_confidence,
    l2_confidence,
)


class TestL1Confidence:
    def test_always_one(self):
        assert l1_confidence() == 1.0


class TestL2Confidence:
    def test_identity(self):
        assert l2_confidence(0.75) == 0.75

    def test_clamp_above_one(self):
        assert l2_confidence(1.5) == 1.0

    def test_clamp_below_zero(self):
        assert l2_confidence(-0.5) == 0.0

    def test_zero(self):
        assert l2_confidence(0.0) == 0.0

    def test_one(self):
        assert l2_confidence(1.0) == 1.0


class TestReviewThreshold:
    def test_below_threshold(self):
        config = ResolverConfig(review_threshold=0.85)
        assert is_below_review_threshold(0.5, config) is True

    def test_at_threshold(self):
        config = ResolverConfig(review_threshold=0.85)
        assert is_below_review_threshold(0.85, config) is False

    def test_above_threshold(self):
        config = ResolverConfig(review_threshold=0.85)
        assert is_below_review_threshold(0.95, config) is False

    def test_threshold_from_config(self):
        """Threshold must come from config, not hardcoded (INV-011)."""
        config_low = ResolverConfig(review_threshold=0.3)
        config_high = ResolverConfig(review_threshold=0.99)

        assert is_below_review_threshold(0.5, config_low) is False
        assert is_below_review_threshold(0.5, config_high) is True


class TestL2MatchThreshold:
    def test_above_threshold(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        assert is_above_l2_match_threshold(0.8, config) is True

    def test_at_threshold(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        assert is_above_l2_match_threshold(0.6, config) is True

    def test_below_threshold(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        assert is_above_l2_match_threshold(0.5, config) is False
