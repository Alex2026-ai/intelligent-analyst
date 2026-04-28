"""Tests for export request and response models."""

import pytest
from pydantic import ValidationError

from ia_shared.models.export import (
    ExportFormat,
    ExportRequest,
    ExportResponse,
    ExportStatus,
)


class TestExportFormat:
    def test_all_values(self):
        assert set(ExportFormat) == {
            ExportFormat.PDF,
            ExportFormat.JSON,
            ExportFormat.CSV,
        }


class TestExportStatus:
    def test_all_values(self):
        assert set(ExportStatus) == {
            ExportStatus.QUEUED,
            ExportStatus.GENERATING,
            ExportStatus.COMPLETE,
            ExportStatus.FAILED,
        }


class TestExportRequest:
    def test_valid_defaults(self):
        req = ExportRequest(
            resolution_id="550e8400-e29b-41d4-a716-446655440000",
            format=ExportFormat.PDF,
        )
        assert req.include_evidence is True
        assert req.include_source_document is False

    def test_all_formats(self):
        for fmt in ExportFormat:
            req = ExportRequest(
                resolution_id="550e8400-e29b-41d4-a716-446655440000",
                format=fmt,
            )
            assert req.format == fmt

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            ExportRequest(
                resolution_id="550e8400-e29b-41d4-a716-446655440000",
                format="docx",
            )

    def test_no_tenant_id_field(self):
        """Request body must not contain tenant_id (INV-005)."""
        assert "tenant_id" not in ExportRequest.model_fields

    def test_include_source_document(self):
        req = ExportRequest(
            resolution_id="r1",
            format=ExportFormat.JSON,
            include_evidence=False,
            include_source_document=True,
        )
        assert req.include_source_document is True
        assert req.include_evidence is False


class TestExportResponse:
    def test_queued(self):
        resp = ExportResponse(
            export_id="e1",
            status=ExportStatus.QUEUED,
            format=ExportFormat.PDF,
            estimated_completion_seconds=30,
            created_at="2026-03-21T10:00:00Z",
        )
        assert resp.download_url is None
        assert resp.completed_at is None

    def test_complete(self):
        resp = ExportResponse(
            export_id="e1",
            status=ExportStatus.COMPLETE,
            format=ExportFormat.CSV,
            download_url="https://storage.googleapis.com/bucket/file?sig=abc",
            created_at="2026-03-21T10:00:00Z",
            completed_at="2026-03-21T10:01:00Z",
        )
        assert resp.download_url is not None
        assert resp.error is None

    def test_failed(self):
        resp = ExportResponse(
            export_id="e1",
            status=ExportStatus.FAILED,
            format=ExportFormat.JSON,
            error="Evidence chain integrity check failed",
            created_at="2026-03-21T10:00:00Z",
            completed_at="2026-03-21T10:00:30Z",
        )
        assert resp.error is not None
        assert resp.download_url is None
