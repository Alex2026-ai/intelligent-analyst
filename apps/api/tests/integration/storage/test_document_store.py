"""Tests for GCS document store."""

import pytest
from apps.api.src.storage.gcs.document_store import DocumentStore, MAX_DOCUMENT_SIZE


class TestDocumentStore:
    def test_upload_and_download(self, gcs):
        store = DocumentStore(gcs, "t1")
        data = b"PDF content here"
        store.upload("d1", "report.pdf", data)
        result = store.download("d1", "report.pdf")
        assert result == data

    def test_upload_size_limit(self, gcs):
        store = DocumentStore(gcs, "t1")
        with pytest.raises(ValueError, match="limit"):
            store.upload("d1", "huge.pdf", b"x" * (MAX_DOCUMENT_SIZE + 1))

    def test_download_not_found(self, gcs):
        store = DocumentStore(gcs, "t1")
        with pytest.raises(FileNotFoundError):
            store.download("d1", "missing.pdf")

    def test_tenant_scoped_path(self, gcs):
        store = DocumentStore(gcs, "t1")
        ref = store.get_reference("d1", "report.pdf")
        assert "tenants/t1/docs/d1/report.pdf" == ref

    def test_different_tenants_isolated(self, gcs):
        store_a = DocumentStore(gcs, "t-a")
        store_b = DocumentStore(gcs, "t-b")
        store_a.upload("d1", "file.pdf", b"tenant A data")
        with pytest.raises(FileNotFoundError):
            store_b.download("d1", "file.pdf")
