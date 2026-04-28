"""Tests for L1 rules engine."""

from apps.api.src.resolver.l1_rules import resolve_l1
from apps.api.tests.unit.resolver.conftest import SAMPLE_RULE_SET, RULE_SET_VERSION


class TestL1RuleMatching:
    def test_exact_content_match(self):
        result = resolve_l1(
            content="This document contains a known OFAC sanctions violation for Entity XYZ.",
            document_type="regulatory",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None
        assert result.confidence == 1.0
        assert result.layer_used == 1
        assert "OFAC" in result.resolution

    def test_regex_pattern_match(self):
        result = resolve_l1(
            content="NOTICE: SEC Form 10-K filing required by March 31, 2026.",
            document_type="regulatory",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None
        assert result.confidence == 1.0
        assert "SEC" in result.resolution

    def test_regex_10q_variant(self):
        result = resolve_l1(
            content="SEC Form 10-Q quarterly report deadline approaching.",
            document_type="regulatory",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None
        assert result.layer_used == 1

    def test_no_match_returns_none(self):
        result = resolve_l1(
            content="Quarterly earnings report with strong revenue growth.",
            document_type="financial",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is None

    def test_wrong_document_type_no_match(self):
        """Rule requires regulatory type — financial type should not match."""
        result = resolve_l1(
            content="This document contains a known OFAC sanctions violation.",
            document_type="financial",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is None

    def test_case_insensitive_content_match(self):
        result = resolve_l1(
            content="Contains an ofac SANCTIONS VIOLATION notice.",
            document_type="regulatory",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None

    def test_empty_rule_set(self):
        result = resolve_l1(
            content="Any content",
            document_type="regulatory",
            metadata={},
            rule_set=[],
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is None

    def test_first_matching_rule_wins(self):
        """When multiple rules could match, first one in order wins."""
        dual_rules = [
            {
                "id": "FIRST",
                "condition": {"content_contains": "OFAC"},
                "resolution": "First rule resolution",
            },
            {
                "id": "SECOND",
                "condition": {"content_contains": "OFAC"},
                "resolution": "Second rule resolution",
            },
        ]
        result = resolve_l1(
            content="OFAC violation",
            document_type="regulatory",
            metadata={},
            rule_set=dual_rules,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None
        assert result.resolution == "First rule resolution"


class TestL1Evidence:
    def test_match_produces_evidence(self):
        result = resolve_l1(
            content="OFAC sanctions violation detected.",
            document_type="regulatory",
            metadata={},
            rule_set=SAMPLE_RULE_SET,
            rule_set_version=RULE_SET_VERSION,
        )
        assert result is not None
        assert len(result.evidence) == 1
        ev = result.evidence[0]
        assert ev.node_type == "transformation"
        assert ev.data["step"] == "l1_rule_match"
        assert ev.data["rule_id"] == "R-001"
        assert ev.data["rule_set_version"] == RULE_SET_VERSION
        assert ev.data["matched"] is True


class TestL1ConditionTypes:
    def test_any_of_condition(self):
        rules = [
            {
                "id": "ANY",
                "condition": {
                    "any_of": [
                        {"content_contains": "alpha"},
                        {"content_contains": "beta"},
                    ]
                },
                "resolution": "matched any_of",
            }
        ]
        result = resolve_l1("contains beta keyword", "regulatory", {}, rules, "1.0")
        assert result is not None
        assert result.resolution == "matched any_of"

    def test_any_of_no_match(self):
        rules = [
            {
                "id": "ANY",
                "condition": {
                    "any_of": [
                        {"content_contains": "alpha"},
                        {"content_contains": "beta"},
                    ]
                },
                "resolution": "matched",
            }
        ]
        result = resolve_l1("contains gamma keyword", "regulatory", {}, rules, "1.0")
        assert result is None

    def test_nested_all_of(self):
        rules = [
            {
                "id": "NESTED",
                "condition": {
                    "all_of": [
                        {"document_type_equals": "compliance"},
                        {"content_contains": "AML"},
                        {"content_pattern": r"\d{4}"},
                    ]
                },
                "resolution": "nested match",
            }
        ]
        result = resolve_l1("AML review for year 2025", "compliance", {}, rules, "1.0")
        assert result is not None

        result2 = resolve_l1("AML review ongoing", "compliance", {}, rules, "1.0")
        assert result2 is None  # missing year pattern
