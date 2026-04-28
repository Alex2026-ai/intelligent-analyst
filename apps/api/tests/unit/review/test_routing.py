"""Tests for case routing from resolver."""

from apps.api.src.review.routing import create_review_case, REASON_TO_PRIORITY


class TestCaseRouting:
    def test_low_confidence_creates_standard(self):
        case = create_review_case("r1", "ec1", "low_confidence")
        assert case["priority"] == "standard"
        assert case["status"] == "pending"

    def test_high_impact_creates_high(self):
        case = create_review_case("r1", "ec1", "high_impact")
        assert case["priority"] == "high"

    def test_llm_unavailable_creates_high(self):
        case = create_review_case("r1", "ec1", "llm_unavailable")
        assert case["priority"] == "high"

    def test_force_review_creates_standard(self):
        case = create_review_case("r1", "ec1", "force_review")
        assert case["priority"] == "standard"

    def test_has_sla_deadline(self):
        case = create_review_case("r1", "ec1", "low_confidence")
        assert case["sla_deadline"] is not None
        assert case["sla_deadline"] > case["created_at"]

    def test_unknown_reason_defaults_standard(self):
        case = create_review_case("r1", "ec1", "unknown_reason")
        assert case["priority"] == "standard"

    def test_case_has_unique_id(self):
        c1 = create_review_case("r1", "ec1", "low_confidence")
        c2 = create_review_case("r2", "ec2", "low_confidence")
        assert c1["case_id"] != c2["case_id"]
