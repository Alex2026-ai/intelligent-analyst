"""Tests for auto-assignment — round-robin, capacity, kill switch."""

from apps.api.src.review.assignment import ReviewAssigner


class TestRoundRobin:
    def test_assigns_first_reviewer(self):
        assigner = ReviewAssigner(max_active_per_reviewer=5)
        reviewers = [{"user_id": "r1"}, {"user_id": "r2"}]
        result = assigner.assign(reviewers, {})
        assert result == "r1"

    def test_round_robin_rotates(self):
        assigner = ReviewAssigner()
        reviewers = [{"user_id": "r1"}, {"user_id": "r2"}, {"user_id": "r3"}]
        r1 = assigner.assign(reviewers, {})
        r2 = assigner.assign(reviewers, {})
        r3 = assigner.assign(reviewers, {})
        assert [r1, r2, r3] == ["r1", "r2", "r3"]

    def test_skips_at_capacity(self):
        assigner = ReviewAssigner(max_active_per_reviewer=2)
        reviewers = [{"user_id": "r1"}, {"user_id": "r2"}]
        result = assigner.assign(reviewers, {"r1": 2})
        assert result == "r2"

    def test_none_when_all_at_capacity(self):
        assigner = ReviewAssigner(max_active_per_reviewer=1)
        reviewers = [{"user_id": "r1"}, {"user_id": "r2"}]
        result = assigner.assign(reviewers, {"r1": 1, "r2": 1})
        assert result is None

    def test_none_with_empty_reviewers(self):
        assigner = ReviewAssigner()
        assert assigner.assign([], {}) is None


class TestKillSwitch:
    def test_disabled_returns_none(self):
        assigner = ReviewAssigner(assignment_enabled=False)
        reviewers = [{"user_id": "r1"}]
        assert assigner.assign(reviewers, {}) is None

    def test_disable_then_enable(self):
        assigner = ReviewAssigner()
        assigner.disable()
        assert assigner.assign([{"user_id": "r1"}], {}) is None
        assigner.enable()
        assert assigner.assign([{"user_id": "r1"}], {}) == "r1"
