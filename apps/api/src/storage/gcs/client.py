"""GCS client abstraction — in-memory for testing."""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BlobMetadata:
    """Metadata for a stored blob."""

    name: str
    size: int
    content_type: str
    md5_hash: str
    created_at: float


class InMemoryGCS:
    """In-memory GCS-like client for testing.

    Supports tenant-scoped paths and signed URL generation.
    """

    def __init__(self, bucket_name: str = "ia-us-central1-source-documents") -> None:
        self._bucket_name = bucket_name
        self._blobs: dict[str, tuple[bytes, BlobMetadata]] = {}

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def upload(
        self,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> BlobMetadata:
        """Upload data to a path."""
        md5 = hashlib.md5(data).hexdigest()
        metadata = BlobMetadata(
            name=path,
            size=len(data),
            content_type=content_type,
            md5_hash=md5,
            created_at=time.time(),
        )
        self._blobs[path] = (copy.copy(data), metadata)
        return metadata

    def download(self, path: str) -> bytes:
        """Download data from a path.

        Raises:
            FileNotFoundError: If blob doesn't exist.
        """
        if path not in self._blobs:
            raise FileNotFoundError(f"Blob not found: {path}")
        return copy.copy(self._blobs[path][0])

    def exists(self, path: str) -> bool:
        return path in self._blobs

    def get_metadata(self, path: str) -> Optional[BlobMetadata]:
        if path not in self._blobs:
            return None
        return self._blobs[path][1]

    def generate_signed_url(self, path: str, ttl_seconds: int = 900) -> str:
        """Generate a mock signed URL (15-minute TTL)."""
        if path not in self._blobs:
            raise FileNotFoundError(f"Blob not found: {path}")
        expiry = int(time.time()) + ttl_seconds
        return f"https://storage.googleapis.com/{self._bucket_name}/{path}?sig=mock&exp={expiry}"

    def delete(self, path: str) -> None:
        self._blobs.pop(path, None)

    def clear(self) -> None:
        self._blobs.clear()
