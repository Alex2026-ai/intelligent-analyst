"""Export metadata repository — tenant-scoped CRUD.

Async-safe: all Firestore operations use _await_if_needed()
for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.base import BaseRepository

COLLECTION = "exports"


class ExportRepository(BaseRepository):
    """Tenant-scoped export metadata storage."""

    async def create(
        self,
        export_id: str,
        resolution_id: str,
        format: str,
        status: str = "queued",
    ) -> dict[str, Any]:
        data = self._with_schema_version({
            "export_id": export_id,
            "resolution_id": resolution_id,
            "format": format,
            "status": status,
            "artifact_ref": None,
            "created_at": self._now(),
            "completed_at": None,
        })
        await self._await_if_needed(
            self._collection(COLLECTION).document(export_id).set(data)
        )
        return data

    async def get(self, export_id: str) -> dict[str, Any]:
        doc = self._collection(COLLECTION).document(export_id).get()
        data = await self._await_if_needed(doc)
        if data is None:
            raise DocumentNotFoundError(COLLECTION, export_id)
        if hasattr(data, "to_dict"):
            data = data.to_dict()
            if data is None:
                raise DocumentNotFoundError(COLLECTION, export_id)
        return data

    async def update_status(self, export_id: str, status: str, artifact_ref: str | None = None) -> None:
        update = {"status": status}
        if artifact_ref:
            update["artifact_ref"] = artifact_ref
        if status in ("complete", "failed"):
            update["completed_at"] = self._now()
        await self._await_if_needed(
            self._collection(COLLECTION).document(export_id).update(update)
        )
