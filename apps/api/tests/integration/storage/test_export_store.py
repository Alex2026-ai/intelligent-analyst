"""Tests for GCS export store — signed URL generation."""

import pytest
from apps.api.src.storage.gcs.export_store import ExportStore


class TestExportStore:
    def test_store_and_download_url(self, gcs):
        store = ExportStore(gcs, "t1")
        store.store_artifact("e1", "report.pdf", b"PDF bytes")
        url = store.generate_download_url("e1", "report.pdf")
        assert "storage.googleapis.com" in url
        assert "sig=" in url
        assert "exp=" in url

    def test_signed_url_not_found(self, gcs):
        store = ExportStore(gcs, "t1")
        with pytest.raises(FileNotFoundError):
            store.generate_download_url("e1", "missing.pdf")

    def test_tenant_scoped_path(self, gcs):
        store = ExportStore(gcs, "t1")
        ref = store.get_reference("e1", "report.pdf")
        assert ref == "tenants/t1/exports/e1/report.pdf"
