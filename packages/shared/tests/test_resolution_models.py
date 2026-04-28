"""Tests for resolution request and response models."""

import pytest
from pydantic import ValidationError

from ia_shared.models.resolution import (
    BatchConfig,
    BatchItemStatus,
    BatchResolutionRequest,
    BatchResolutionResponse,
    BatchResultItem,
    DocumentMetadata,
    DocumentType,
    Priority,
    ResolutionRequest,
    ResolutionResponse,
    ResolutionStatus,
    ReviewReason,
)
from ia_shared.constants import MAX_BATCH_SIZE, MAX_DOCUMENT_CONTENT_BYTES


class TestDocumentType:
    def test_all_values(self):
        assert set(DocumentType) == {
            DocumentType.REGULATORY,
            DocumentType.COMPLIANCE,
            DocumentType.FINANCIAL,
            DocumentType.MEDICAL,
        }

    def test_string_values(self):
        assert DocumentType.REGULATORY.value == "regulatory"
        assert DocumentType.COMPLIANCE.value == "compliance"
        assert DocumentType.FINANCIAL.value == "financial"
        assert DocumentType.MEDICAL.value == "medical"


class TestPriority:
    def test_all_values(self):
        assert set(Priority) == {Priority.STANDARD, Priority.HIGH, Priority.URGENT}


class TestResolutionRequest:
    def test_valid_minimal(self):
        req = ResolutionRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            document_type=DocumentType.REGULATORY,
            content="Test document content",
        )
        assert req.document_id == "550e8400-e29b-41d4-a716-446655440000"
        assert req.document_type == DocumentType.REGULATORY
        assert req.metadata.priority == Priority.STANDARD
        assert req.metadata.force_review is False

    def test_valid_full(self):
        req = ResolutionRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            document_type=DocumentType.MEDICAL,
            content="Full document",
            metadata=DocumentMetadata(
                source="test-system",
                priority=Priority.URGENT,
                force_review=True,
            ),
        )
        assert req.metadata.source == "test-system"
        assert req.metadata.priority == Priority.URGENT
        assert req.metadata.force_review is True

    def test_missing_document_id(self):
        with pytest.raises(ValidationError):
            ResolutionRequest(
                document_type=DocumentType.REGULATORY,
                content="test",
            )

    def test_missing_content(self):
        with pytest.raises(ValidationError):
            ResolutionRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                document_type=DocumentType.REGULATORY,
            )

    def test_invalid_document_type(self):
        with pytest.raises(ValidationError):
            ResolutionRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                document_type="unknown",
                content="test",
            )

    def test_content_too_large(self):
        with pytest.raises(ValidationError):
            ResolutionRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                document_type=DocumentType.REGULATORY,
                content="x" * (MAX_DOCUMENT_CONTENT_BYTES + 1),
            )

    def test_invalid_uuid_format(self):
        with pytest.raises(ValidationError):
            ResolutionRequest(
                document_id="not-a-uuid",
                document_type=DocumentType.REGULATORY,
                content="test",
            )

    def test_no_tenant_id_field(self):
        """tenant_id must never appear in request bodies (INV-005)."""
        assert "tenant_id" not in ResolutionRequest.model_fields


class TestBatchResolutionRequest:
    def test_valid(self):
        doc = ResolutionRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            document_type=DocumentType.FINANCIAL,
            content="test",
        )
        batch = BatchResolutionRequest(documents=[doc])
        assert len(batch.documents) == 1
        assert batch.batch_config.max_parallel == 5
        assert batch.batch_config.stop_on_error is False

    def test_empty_documents_rejected(self):
        with pytest.raises(ValidationError):
            BatchResolutionRequest(documents=[])

    def test_exceeds_max_batch_size(self):
        doc = ResolutionRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            document_type=DocumentType.REGULATORY,
            content="test",
        )
        with pytest.raises(ValidationError):
            BatchResolutionRequest(documents=[doc] * (MAX_BATCH_SIZE + 1))

    def test_custom_batch_config(self):
        doc = ResolutionRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            document_type=DocumentType.REGULATORY,
            content="test",
        )
        batch = BatchResolutionRequest(
            documents=[doc],
            batch_config=BatchConfig(max_parallel=10, stop_on_error=True),
        )
        assert batch.batch_config.max_parallel == 10
        assert batch.batch_config.stop_on_error is True

    def test_max_parallel_bounds(self):
        with pytest.raises(ValidationError):
            BatchConfig(max_parallel=0)
        with pytest.raises(ValidationError):
            BatchConfig(max_parallel=11)


class TestResolutionResponse:
    def test_valid_resolved(self):
        resp = ResolutionResponse(
            resolution_id="550e8400-e29b-41d4-a716-446655440000",
            status=ResolutionStatus.RESOLVED,
            layer_used=2,
            confidence=0.92,
            resolution="Matched to canonical entity",
            evidence_chain_id="660e8400-e29b-41d4-a716-446655440000",
            created_at="2026-03-21T10:00:00Z",
        )
        assert resp.status == ResolutionStatus.RESOLVED
        assert resp.review_reason is None

    def test_valid_routed_to_review(self):
        resp = ResolutionResponse(
            resolution_id="550e8400-e29b-41d4-a716-446655440000",
            status=ResolutionStatus.ROUTED_TO_REVIEW,
            layer_used=4,
            confidence=0.3,
            resolution=None,
            review_reason=ReviewReason.LOW_CONFIDENCE,
            evidence_chain_id="660e8400-e29b-41d4-a716-446655440000",
            created_at="2026-03-21T10:00:00Z",
        )
        assert resp.review_reason == ReviewReason.LOW_CONFIDENCE

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ResolutionResponse(
                resolution_id="550e8400-e29b-41d4-a716-446655440000",
                status=ResolutionStatus.RESOLVED,
                layer_used=1,
                confidence=1.5,
                evidence_chain_id="660e8400-e29b-41d4-a716-446655440000",
                created_at="2026-03-21T10:00:00Z",
            )

    def test_layer_bounds(self):
        with pytest.raises(ValidationError):
            ResolutionResponse(
                resolution_id="550e8400-e29b-41d4-a716-446655440000",
                status=ResolutionStatus.RESOLVED,
                layer_used=0,
                confidence=0.9,
                evidence_chain_id="660e8400-e29b-41d4-a716-446655440000",
                created_at="2026-03-21T10:00:00Z",
            )
        with pytest.raises(ValidationError):
            ResolutionResponse(
                resolution_id="550e8400-e29b-41d4-a716-446655440000",
                status=ResolutionStatus.RESOLVED,
                layer_used=5,
                confidence=0.9,
                evidence_chain_id="660e8400-e29b-41d4-a716-446655440000",
                created_at="2026-03-21T10:00:00Z",
            )


class TestBatchResolutionResponse:
    def test_valid(self):
        resp = BatchResolutionResponse(
            batch_id="770e8400-e29b-41d4-a716-446655440000",
            total=3,
            resolved=2,
            routed_to_review=1,
            failed=0,
            results=[
                BatchResultItem(
                    document_id="a",
                    resolution_id="b",
                    status=BatchItemStatus.RESOLVED,
                    layer_used=1,
                    confidence=1.0,
                ),
                BatchResultItem(
                    document_id="c",
                    resolution_id="d",
                    status=BatchItemStatus.ROUTED_TO_REVIEW,
                    layer_used=4,
                    confidence=0.3,
                ),
                BatchResultItem(
                    document_id="e",
                    resolution_id="f",
                    status=BatchItemStatus.FAILED,
                    error="Processing timeout",
                ),
            ],
            created_at="2026-03-21T10:00:00Z",
        )
        assert resp.total == 3
        assert resp.results[2].error == "Processing timeout"
        assert resp.results[2].layer_used is None
