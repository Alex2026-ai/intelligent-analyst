"""Real GCS client wrapping google-cloud-storage.

Uses Application Default Credentials (ADC) — no secrets in code (FP-004).
"""

from __future__ import annotations

import hashlib
import time
from datetime import timedelta
from typing import Optional

from google.cloud import storage

from apps.api.src.storage.gcs.client import BlobMetadata


class GCSClient:
    """Production GCS client.

    Satisfies GCSClientProtocol.
    """

    def __init__(self, bucket_name: str) -> None:
        self._storage_client = storage.Client()
        self._bucket = self._storage_client.bucket(bucket_name)
        self._bucket_name = bucket_name

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def upload(
        self, path: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> BlobMetadata:
        """Upload data to GCS."""
        blob = self._bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
        md5 = hashlib.md5(data).hexdigest()
        return BlobMetadata(
            name=path, size=len(data), content_type=content_type,
            md5_hash=md5, created_at=time.time(),
        )

    def download(self, path: str) -> bytes:
        """Download data from GCS."""
        blob = self._bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(f"Blob not found: {path}")
        return blob.download_as_bytes()

    def exists(self, path: str) -> bool:
        return self._bucket.blob(path).exists()

    def get_metadata(self, path: str) -> Optional[BlobMetadata]:
        blob = self._bucket.blob(path)
        if not blob.exists():
            return None
        blob.reload()
        return BlobMetadata(
            name=path,
            size=blob.size or 0,
            content_type=blob.content_type or "",
            md5_hash=blob.md5_hash or "",
            created_at=blob.time_created.timestamp() if blob.time_created else 0,
        )

    def generate_signed_url(self, path: str, ttl_seconds: int = 900) -> str:
        """Generate a signed download URL."""
        blob = self._bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(f"Blob not found: {path}")
        return blob.generate_signed_url(
            expiration=timedelta(seconds=ttl_seconds), method="GET"
        )

    def delete(self, path: str) -> None:
        blob = self._bucket.blob(path)
        if blob.exists():
            blob.delete()
