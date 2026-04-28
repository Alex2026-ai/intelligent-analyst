"""Resolution repository — CRUD for resolutions (tenant-scoped).

Async-safe: all Firestore operations use _await_if_needed() and
_collect_stream() for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.base import BaseRepository

COLLECTION = "resolutions"


class ResolutionRepository(BaseRepository):
    """Tenant-scoped resolution storage."""

    async def create(
        self,
        resolution_id: str,
        document_id: str,
        status: str,
        layer_used: int | None,
        confidence: float,
        evidence_chain_id: str,
        resolution_text: str | None = None,
        review_reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a new resolution record."""
        data = self._with_schema_version({
            "resolution_id": resolution_id,
            "document_id": document_id,
            "status": status,
            "layer_used": layer_used,
            "confidence": confidence,
            "evidence_chain_id": evidence_chain_id,
            "resolution": resolution_text,
            "review_reason": review_reason,
            "created_at": self._now(),
            "updated_at": self._now(),
        })
        await self._await_if_needed(
            self._collection(COLLECTION).document(resolution_id).set(data)
        )
        return data

    async def get(self, resolution_id: str) -> dict[str, Any]:
        """Get a resolution by ID."""
        doc = self._collection(COLLECTION).document(resolution_id).get()
        data = await self._await_if_needed(doc)
        if data is None:
            raise DocumentNotFoundError(COLLECTION, resolution_id)
        if hasattr(data, "to_dict"):
            data = data.to_dict()
            if data is None:
                raise DocumentNotFoundError(COLLECTION, resolution_id)
        return data

    async def get_by_document_id(self, document_id: str) -> Optional[dict[str, Any]]:
        """Find resolution by document_id."""
        stream = self._collection(COLLECTION).where("document_id", "==", document_id).stream()
        results = await self._collect_stream(stream)
        if results:
            return results[0][1]
        return None

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        """List resolutions with a given status."""
        stream = self._collection(COLLECTION).where("status", "==", status).stream()
        results = await self._collect_stream(stream)
        return [data for _, data in results]
