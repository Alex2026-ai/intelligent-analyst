"""Audit log repository — append-only, tenant-scoped.

No update or delete operations exist (by design).

Async-safe: all Firestore operations use _await_if_needed() and
_collect_stream() for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.storage.firestore.base import BaseRepository

COLLECTION = "audit_log"


class AuditRepository(BaseRepository):
    """Append-only audit log. No update() or delete() methods."""

    async def append(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append an audit entry. This is the only write operation."""
        audit_id = self._new_id()
        data = self._with_schema_version({
            "audit_id": audit_id,
            "timestamp": self._now(),
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
        })
        await self._await_if_needed(
            self._collection(COLLECTION).document(audit_id).set(data)
        )
        return data

    async def list_by_resource(self, resource_type: str, resource_id: str) -> list[dict[str, Any]]:
        """Query audit entries for a specific resource."""
        stream = (
            self._collection(COLLECTION)
            .where("resource_type", "==", resource_type)
            .stream()
        )
        results = await self._collect_stream(stream)
        return [
            data for _, data in results
            if data.get("resource_id") == resource_id
        ]

    async def list_all(self) -> list[dict[str, Any]]:
        """List all audit entries for this tenant."""
        stream = self._collection(COLLECTION).stream()
        results = await self._collect_stream(stream)
        return [data for _, data in results]
