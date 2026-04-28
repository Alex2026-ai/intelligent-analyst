"""Protocol for GCS client abstraction.

Allows InMemoryGCS (testing) and GCSClient (production) to be swapped.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from apps.api.src.storage.gcs.client import BlobMetadata


@runtime_checkable
class GCSClientProtocol(Protocol):
    """Minimal interface that both InMemoryGCS and real GCSClient satisfy."""

    @property
    def bucket_name(self) -> str: ...

    def upload(self, path: str, data: bytes, content_type: str = ...) -> BlobMetadata: ...

    def download(self, path: str) -> bytes: ...

    def exists(self, path: str) -> bool: ...

    def get_metadata(self, path: str) -> Optional[BlobMetadata]: ...

    def generate_signed_url(self, path: str, ttl_seconds: int = ...) -> str: ...

    def delete(self, path: str) -> None: ...
