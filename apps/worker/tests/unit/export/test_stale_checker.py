"""Tests for stale case checker."""

from datetime import datetime, timedelta, timezone
from apps.worker.src.review.stale_checker import check_and_reassign


def _breached_case(case_id="c1", assigned_to="r1", reassignment_count=0):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {
        "case_id": case_id,
        "status": "assigned",
        "assigned_to": assigned_to,
        "sla_deadline": past,
        "reassignment_count": reassignment_count,
    }


class TestStaleChecker:
    def test_reassigns_breached_case(self):
        cases = [_breached_case()]
        actions = check_and_reassign(cases, ["r2", "r3"])
        assert len(actions) == 1
        assert actions[0]["action"] == "reassign"
        assert actions[0]["new_reviewer"] == "r2"

    def test_escalates_after_max_reassignments(self):
        cases = [_breached_case(reassignment_count=2)]
        actions = check_and_reassign(cases, ["r2"])
        assert actions[0]["action"] == "escalate"

    def test_escalates_no_reviewers(self):
        cases = [_breached_case()]
        actions = check_and_reassign(cases, [])
        assert actions[0]["action"] == "escalate"

    def test_skips_non_breached(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        cases = [{"case_id": "c1", "status": "pending", "sla_deadline": future}]
        actions = check_and_reassign(cases, ["r1"])
        assert len(actions) == 0

    def test_reassign_excludes_current_reviewer(self):
        cases = [_breached_case(assigned_to="r1")]
        actions = check_and_reassign(cases, ["r1", "r2"])
        assert actions[0]["new_reviewer"] == "r2"
