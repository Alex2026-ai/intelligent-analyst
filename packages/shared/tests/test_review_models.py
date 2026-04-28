"""Tests for review queue and decision models."""

import pytest
from pydantic import ValidationError

from ia_shared.models.review import (
    CasePriority,
    CaseStatus,
    Decision,
    QueueStats,
    ReviewCase,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueParams,
    ReviewQueueResponse,
    ReviewReason,
)
from ia_shared.constants import MIN_REVIEW_NOTES_LENGTH


class TestCaseStatus:
    def test_all_values(self):
        assert set(CaseStatus) == {
            CaseStatus.PENDING,
            CaseStatus.ASSIGNED,
            CaseStatus.DECIDED,
            CaseStatus.ESCALATED,
        }


class TestDecision:
    def test_all_values(self):
        assert set(Decision) == {
            Decision.APPROVE,
            Decision.REJECT,
            Decision.ESCALATE,
            Decision.REQUEST_MORE_EVIDENCE,
            Decision.REOPEN,
        }

    def test_exhaustive(self):
        """No catch-all 'other' value."""
        assert len(Decision) == 5


class TestReviewReason:
    def test_all_values(self):
        assert set(ReviewReason) == {
            ReviewReason.LOW_CONFIDENCE,
            ReviewReason.HIGH_IMPACT,
            ReviewReason.FORCE_REVIEW,
            ReviewReason.LLM_UNAVAILABLE,
        }


class TestReviewDecisionRequest:
    def test_valid(self):
        req = ReviewDecisionRequest(
            decision=Decision.APPROVE,
            notes="Reviewed all evidence nodes and confirmed match.",
            evidence_reviewed=["node-1", "node-2"],
        )
        assert req.decision == Decision.APPROVE
        assert len(req.evidence_reviewed) == 2

    def test_notes_too_short(self):
        with pytest.raises(ValidationError):
            ReviewDecisionRequest(
                decision=Decision.REJECT,
                notes="short",
            )

    def test_notes_exactly_minimum(self):
        req = ReviewDecisionRequest(
            decision=Decision.APPROVE,
            notes="x" * MIN_REVIEW_NOTES_LENGTH,
        )
        assert len(req.notes) == MIN_REVIEW_NOTES_LENGTH

    def test_no_tenant_id_field(self):
        """Request body must not contain tenant_id (INV-005)."""
        assert "tenant_id" not in ReviewDecisionRequest.model_fields

    def test_empty_evidence_reviewed_allowed(self):
        req = ReviewDecisionRequest(
            decision=Decision.ESCALATE,
            notes="Escalating due to complexity beyond my expertise.",
        )
        assert req.evidence_reviewed == []


class TestReviewCase:
    def test_valid(self):
        case = ReviewCase(
            case_id="c1",
            resolution_id="r1",
            evidence_chain_id="e1",
            status=CaseStatus.PENDING,
            priority=CasePriority.HIGH,
            review_reason=ReviewReason.HIGH_IMPACT,
            sla_deadline="2026-03-22T10:00:00Z",
            created_at="2026-03-21T10:00:00Z",
        )
        assert case.assigned_to is None
        assert case.priority == CasePriority.HIGH

    def test_assigned(self):
        case = ReviewCase(
            case_id="c1",
            resolution_id="r1",
            evidence_chain_id="e1",
            status=CaseStatus.ASSIGNED,
            priority=CasePriority.STANDARD,
            review_reason=ReviewReason.LOW_CONFIDENCE,
            assigned_to="user-42",
            sla_deadline="2026-03-22T10:00:00Z",
            created_at="2026-03-21T10:00:00Z",
        )
        assert case.assigned_to == "user-42"


class TestQueueStats:
    def test_valid(self):
        stats = QueueStats(
            total_pending=42,
            total_assigned=15,
            oldest_case_age_hours=4.2,
            sla_breaches=0,
        )
        assert stats.total_pending == 42

    def test_negative_values_rejected(self):
        with pytest.raises(ValidationError):
            QueueStats(
                total_pending=-1,
                total_assigned=0,
                oldest_case_age_hours=0.0,
                sla_breaches=0,
            )


class TestReviewQueueResponse:
    def test_valid(self):
        resp = ReviewQueueResponse(
            cases=[],
            queue_stats=QueueStats(
                total_pending=0,
                total_assigned=0,
                oldest_case_age_hours=0.0,
                sla_breaches=0,
            ),
        )
        assert resp.next_cursor is None


class TestReviewDecisionResponse:
    def test_valid(self):
        resp = ReviewDecisionResponse(
            case_id="c1",
            decision=Decision.APPROVE,
            decided_by="user-42",
            decided_at="2026-03-21T10:00:00Z",
            evidence_chain_updated=True,
        )
        assert resp.decided_by == "user-42"


class TestReviewQueueParams:
    def test_defaults(self):
        params = ReviewQueueParams()
        assert params.status is None
        assert params.priority is None
        assert params.page_size == 50

    def test_with_filters(self):
        params = ReviewQueueParams(
            status=CaseStatus.PENDING,
            priority=CasePriority.URGENT,
            assigned_to="user-1",
        )
        assert params.status == CaseStatus.PENDING
