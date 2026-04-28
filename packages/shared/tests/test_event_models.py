"""Tests for Pub/Sub event models."""

import pytest
from pydantic import ValidationError

from ia_shared.models.events import (
    Event,
    EventType,
    ExportRequestedData,
    ExportRequestedEvent,
    ResolutionCompletedData,
    ResolutionCompletedEvent,
    ReviewDecisionMadeData,
    ReviewDecisionMadeEvent,
)
from ia_shared.constants import EVENT_VERSION


class TestEventType:
    def test_all_values(self):
        assert set(EventType) == {
            EventType.RESOLUTION_COMPLETED,
            EventType.REVIEW_DECISION_MADE,
            EventType.EXPORT_REQUESTED,
        }

    def test_string_values(self):
        assert EventType.RESOLUTION_COMPLETED.value == "resolution.completed"
        assert EventType.REVIEW_DECISION_MADE.value == "review.decision_made"
        assert EventType.EXPORT_REQUESTED.value == "export.requested"


class TestResolutionCompletedEvent:
    def test_valid(self):
        event = ResolutionCompletedEvent(
            event_id="e1",
            timestamp="2026-03-21T10:00:00Z",
            tenant_id="tenant-001",
            correlation_id="trace-123",
            data=ResolutionCompletedData(
                resolution_id="r1",
                document_id="d1",
                status="resolved",
                layer_used=2,
                confidence=0.95,
                evidence_chain_id="ec1",
            ),
        )
        assert event.event_type == EventType.RESOLUTION_COMPLETED
        assert event.version == EVENT_VERSION
        assert event.data.layer_used == 2

    def test_version_field_present(self):
        event = ResolutionCompletedEvent(
            event_id="e1",
            timestamp="2026-03-21T10:00:00Z",
            tenant_id="t1",
            correlation_id="c1",
            data=ResolutionCompletedData(
                resolution_id="r1",
                document_id="d1",
                status="routed_to_review",
                layer_used=4,
                confidence=0.3,
                evidence_chain_id="ec1",
                review_reason="low_confidence",
            ),
        )
        assert event.version == "1.0"

    def test_layer_bounds(self):
        with pytest.raises(ValidationError):
            ResolutionCompletedData(
                resolution_id="r1",
                document_id="d1",
                status="resolved",
                layer_used=0,
                confidence=0.9,
                evidence_chain_id="ec1",
            )


class TestReviewDecisionMadeEvent:
    def test_valid(self):
        event = ReviewDecisionMadeEvent(
            event_id="e2",
            timestamp="2026-03-21T10:00:00Z",
            tenant_id="tenant-001",
            correlation_id="trace-456",
            data=ReviewDecisionMadeData(
                case_id="c1",
                resolution_id="r1",
                decision="approve",
                decided_by="user-42",
                evidence_chain_id="ec1",
            ),
        )
        assert event.event_type == EventType.REVIEW_DECISION_MADE
        assert event.data.decided_by == "user-42"


class TestExportRequestedEvent:
    def test_valid(self):
        event = ExportRequestedEvent(
            event_id="e3",
            timestamp="2026-03-21T10:00:00Z",
            tenant_id="tenant-001",
            correlation_id="trace-789",
            data=ExportRequestedData(
                export_id="ex1",
                resolution_id="r1",
                evidence_chain_id="ec1",
                format="pdf",
                include_evidence=True,
                include_source_document=False,
                requested_by="user-42",
            ),
        )
        assert event.event_type == EventType.EXPORT_REQUESTED
        assert event.data.include_evidence is True


class TestEventEnvelope:
    def test_resolution_completed_via_envelope(self):
        event = Event(
            event_type=EventType.RESOLUTION_COMPLETED,
            event_id="e1",
            timestamp="2026-03-21T10:00:00Z",
            tenant_id="t1",
            correlation_id="c1",
            data=ResolutionCompletedData(
                resolution_id="r1",
                document_id="d1",
                status="resolved",
                layer_used=1,
                confidence=1.0,
                evidence_chain_id="ec1",
            ),
        )
        assert event.event_type == EventType.RESOLUTION_COMPLETED

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Event(
                event_type=EventType.RESOLUTION_COMPLETED,
                # missing event_id, timestamp, tenant_id, correlation_id, data
            )

    def test_tenant_id_required(self):
        """Events must always include tenant_id."""
        assert "tenant_id" in Event.model_fields
