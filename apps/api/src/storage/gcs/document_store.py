"""Source document upload/download — tenant-scoped GCS paths."""

from __future__ import annotations

from apps.api.src.storage.gcs.client import BlobMetadata
from apps.api.src.storage.gcs.protocol import GCSClientProtocol

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB


class DocumentStore:
    """Tenant-scoped source document storage."""

    def __init__(self, gcs: GCSClientProtocol, tenant_id: str, region: str = "us-central1") -> None:
        self._gcs = gcs
        self._tenant_id = tenant_id
        self._region = region

    def _path(self, document_id: str, filename: str) -> str:
        return f"tenants/{self._tenant_id}/docs/{document_id}/{filename}"

    def upload(
        self,
        document_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> BlobMetadata:
        """Upload a source document.

        Args:
            document_id: UUID of the document.
            filename: Original filename.
            data: File content bytes.
            content_type: MIME type.

        Returns:
            BlobMetadata with upload details.

        Raises:
            ValueError: If data exceeds 10MB limit.
        """
        if len(data) > MAX_DOCUMENT_SIZE:
            raise ValueError(f"Document exceeds {MAX_DOCUMENT_SIZE} byte limit")
        path = self._path(document_id, filename)
        return self._gcs.upload(path, data, content_type)

    def download(self, document_id: str, filename: str) -> bytes:
        """Download a source document."""
        path = self._path(document_id, filename)
        return self._gcs.download(path)

    def get_reference(self, document_id: str, filename: str) -> str:
        """Get the GCS path reference for evidence chain."""
        return self._path(document_id, filename)
