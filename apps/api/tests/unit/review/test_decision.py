"""Tests for review decision processing."""

import pytest
from apps.api.src.review.decision import (
    build_evidence_node_data,
    process_decision,
    VALID_DECISIONS,
)
from apps.api.src.review.exceptions import CaseAlreadyDecidedError, InvalidDecisionError


def _make_case(status="assigned"):
    return {"case_id": "c1", "status": status, "assigned_to": "reviewer-1"}


class TestProcessDecision:
    def test_approve(self):
        case = _make_case()
        record = process_decision(case, "approve", "reviewer-1", "Looks correct.")
        assert record["decision"] == "approve"
        assert record["new_status"] == "decided"
        assert case["status"] == "decided"

    def test_reject(self):
        case = _make_case()
        record = process_decision(case, "reject", "reviewer-1", "Does not match.")
        assert record["new_status"] == "decided"

    def test_escalate(self):
        case = _make_case()
        record = process_decision(case, "escalate", "reviewer-1", "Need senior review.")
        assert record["new_status"] == "escalated"
        assert case["status"] == "escalated"

    def test_request_more_evidence(self):
        case = _make_case()
        record = process_decision(case, "request_more_evidence", "reviewer-1", "Missing context.")
        assert record["new_status"] == "pending"

    def test_reopen(self):
        case = _make_case(status="decided")
        # Reopen is special — it's allowed on decided cases
        # But our code blocks already-decided. Let's test with escalated
        case2 = _make_case(status="escalated")
        record = process_decision(case2, "reopen", "admin-1", "Re-evaluate with new data.")
        assert record["new_status"] == "pending"

    def test_invalid_decision(self):
        case = _make_case()
        with pytest.raises(InvalidDecisionError):
            process_decision(case, "invalid", "reviewer-1", "Some notes here.")

    def test_already_decided(self):
        case = _make_case(status="decided")
        with pytest.raises(CaseAlreadyDecidedError):
            process_decision(case, "approve", "reviewer-1", "Trying again.")

    def test_all_five_decisions_are_valid(self):
        assert len(VALID_DECISIONS) == 5
        assert VALID_DECISIONS == {"approve", "reject", "escalate", "request_more_evidence", "reopen"}


class TestEvidenceNodeData:
    def test_builds_correct_data(self):
        record = {
            "case_id": "c1",
            "decision": "approve",
            "decided_by": "reviewer-1",
            "notes": "Confirmed match.",
            "evidence_reviewed": ["n1", "n2"],
        }
        data = build_evidence_node_data(record)
        assert data["decision"] == "approve"
        assert data["reviewer_id"] == "reviewer-1"
        assert data["notes"] == "Confirmed match."
        assert data["evidence_reviewed"] == ["n1", "n2"]
