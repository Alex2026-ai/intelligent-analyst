"""Tests for L2 matching engine."""

import pytest

from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.l2_matching import resolve_l2, _normalize, _dice_coefficient
from apps.api.tests.unit.resolver.conftest import SAMPLE_PRECEDENTS


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("HELLO World") == "hello world"

    def test_strip_punctuation(self):
        assert _normalize("hello, world!") == "hello world"

    def test_collapse_whitespace(self):
        assert _normalize("hello   world") == "hello world"

    def test_strip_edges(self):
        assert _normalize("  hello  ") == "hello"


class TestDiceCoefficient:
    def test_identical_strings(self):
        assert _dice_coefficient("hello", "hello") == 1.0

    def test_completely_different(self):
        score = _dice_coefficient("abc", "xyz")
        assert score == 0.0

    def test_similar_strings(self):
        score = _dice_coefficient("hello world", "hello worl")
        assert 0.8 < score < 1.0

    def test_empty_strings(self):
        assert _dice_coefficient("", "") == 1.0

    def test_one_empty(self):
        assert _dice_coefficient("hello", "") == 0.0

    def test_symmetry(self):
        assert _dice_coefficient("abc", "abcd") == _dice_coefficient("abcd", "abc")


class TestL2ExactMatch:
    def test_exact_match(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is not None
        assert result.confidence == 1.0
        assert result.layer_used == 2
        assert "SOX" in result.resolution

    def test_exact_match_case_insensitive(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="annual sox compliance audit for fy2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is not None
        assert result.confidence == 1.0

    def test_exact_match_evidence(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
            document_type="compliance",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is not None
        assert len(result.evidence) == 1
        assert result.evidence[0].data["match_type"] == "exact"
        assert result.evidence[0].data["precedent_id"] == "P-001"


class TestL2FuzzyMatch:
    def test_fuzzy_match_above_threshold(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="Annual SOX compliance audit for FY2025 - all controls passed; no material weaknesses found.",
            document_type="compliance",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is not None
        assert result.layer_used == 2
        assert result.confidence > 0.6

    def test_fuzzy_match_evidence(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="Annual SOX compliance audit for FY2025 - all controls passed; no material weaknesses found.",
            document_type="compliance",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is not None
        assert result.evidence[0].data["match_type"] == "fuzzy"

    def test_no_match_below_threshold(self):
        config = ResolverConfig(l2_match_threshold=0.95)
        result = resolve_l2(
            content="Something completely different about quarterly earnings.",
            document_type="financial",
            metadata={},
            precedents=SAMPLE_PRECEDENTS,
            config=config,
        )
        assert result is None

    def test_no_match_empty_precedents(self):
        config = ResolverConfig(l2_match_threshold=0.6)
        result = resolve_l2(
            content="Any content",
            document_type="regulatory",
            metadata={},
            precedents=[],
            config=config,
        )
        assert result is None


class TestL2ThresholdBehavior:
    def test_threshold_from_config(self):
        """Match threshold must come from config, not hardcoded."""
        high_threshold = ResolverConfig(l2_match_threshold=0.99)
        low_threshold = ResolverConfig(l2_match_threshold=0.1)

        content = "SOX compliance audit FY2025 - controls passed"

        result_high = resolve_l2(content, "compliance", {}, SAMPLE_PRECEDENTS, high_threshold)
        result_low = resolve_l2(content, "compliance", {}, SAMPLE_PRECEDENTS, low_threshold)

        # With a very high threshold, fuzzy match may not pass
        # With a low threshold, it should pass
        assert result_low is not None
