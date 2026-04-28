"""Export artifact storage — signed URL generation, tenant-scoped."""

from __future__ import annotations

from apps.api.src.storage.gcs.client import BlobMetadata
from apps.api.src.storage.gcs.protocol import GCSClientProtocol

EXPORT_URL_TTL_SECONDS = 900  # 15 minutes


class ExportStore:
    """Tenant-scoped export artifact storage with signed URLs."""

    def __init__(self, gcs: GCSClientProtocol, tenant_id: str) -> None:
        self._gcs = gcs
        self._tenant_id = tenant_id

    def _path(self, export_id: str, filename: str) -> str:
        return f"tenants/{self._tenant_id}/exports/{export_id}/{filename}"

    def store_artifact(
        self,
        export_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> BlobMetadata:
        """Store an export artifact."""
        path = self._path(export_id, filename)
        return self._gcs.upload(path, data, content_type)

    def generate_download_url(self, export_id: str, filename: str) -> str:
        """Generate a signed download URL (15-minute TTL)."""
        path = self._path(export_id, filename)
        return self._gcs.generate_signed_url(path, EXPORT_URL_TTL_SECONDS)

    def get_reference(self, export_id: str, filename: str) -> str:
        """Get the GCS path reference."""
        return self._path(export_id, filename)
