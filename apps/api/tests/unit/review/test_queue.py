"""Tests for review queue operations."""

from apps.api.src.review.queue import ReviewQueue
from apps.api.src.review.routing import create_review_case


class TestReviewQueue:
    def test_add_and_get(self):
        q = ReviewQueue()
        case = create_review_case("r1", "ec1", "low_confidence")
        q.add_case(case)
        assert q.get_case(case["case_id"]) is not None

    def test_list_by_status(self):
        q = ReviewQueue()
        c1 = create_review_case("r1", "ec1", "low_confidence")
        c2 = create_review_case("r2", "ec2", "high_impact")
        q.add_case(c1)
        q.add_case(c2)
        pending = q.list_cases(status="pending")
        assert len(pending) == 2

    def test_assign(self):
        q = ReviewQueue()
        case = create_review_case("r1", "ec1", "low_confidence")
        q.add_case(case)
        result = q.assign_case(case["case_id"], "reviewer-1")
        assert result["status"] == "assigned"
        assert result["assigned_to"] == "reviewer-1"

    def test_get_stats(self):
        q = ReviewQueue()
        c1 = create_review_case("r1", "ec1", "low_confidence")
        c2 = create_review_case("r2", "ec2", "high_impact")
        q.add_case(c1)
        q.add_case(c2)
        q.assign_case(c2["case_id"], "reviewer-1")
        stats = q.get_stats()
        assert stats["total_pending"] == 1
        assert stats["total_assigned"] == 1
        assert stats["total"] == 2

    def test_get_nonexistent_returns_none(self):
        q = ReviewQueue()
        assert q.get_case("nonexistent") is None

    def test_filter_by_priority(self):
        q = ReviewQueue()
        c1 = create_review_case("r1", "ec1", "low_confidence")  # standard
        c2 = create_review_case("r2", "ec2", "high_impact")  # high
        q.add_case(c1)
        q.add_case(c2)
        high = q.list_cases(priority="high")
        assert len(high) == 1
