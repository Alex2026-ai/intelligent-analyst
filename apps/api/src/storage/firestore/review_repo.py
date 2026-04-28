"""Review case repository — tenant-scoped CRUD.

Async-safe: all Firestore operations use _await_if_needed() and
_collect_stream() for dual sync/async backend support.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.api.src.storage.exceptions import DocumentNotFoundError
from apps.api.src.storage.firestore.base import BaseRepository

COLLECTION = "review_cases"


class ReviewRepository(BaseRepository):
    """Tenant-scoped review case storage."""

    async def create(
        self,
        case_id: str,
        resolution_id: str,
        evidence_chain_id: str,
        status: str,
        priority: str,
        review_reason: str,
        sla_deadline: str,
    ) -> dict[str, Any]:
        data = self._with_schema_version({
            "case_id": case_id,
            "resolution_id": resolution_id,
            "evidence_chain_id": evidence_chain_id,
            "status": status,
            "priority": priority,
            "review_reason": review_reason,
            "assigned_to": None,
            "sla_deadline": sla_deadline,
            "created_at": self._now(),
        })
        await self._await_if_needed(
            self._collection(COLLECTION).document(case_id).set(data)
        )
        return data

    async def get(self, case_id: str) -> dict[str, Any]:
        doc = self._collection(COLLECTION).document(case_id).get()
        data = await self._await_if_needed(doc)
        if data is None:
            raise DocumentNotFoundError(COLLECTION, case_id)
        if hasattr(data, "to_dict"):
            data = data.to_dict()
            if data is None:
                raise DocumentNotFoundError(COLLECTION, case_id)
        return data

    async def update_status(self, case_id: str, status: str) -> None:
        await self._await_if_needed(
            self._collection(COLLECTION).document(case_id).update({"status": status})
        )

    async def assign(self, case_id: str, reviewer_id: str) -> None:
        await self._await_if_needed(
            self._collection(COLLECTION).document(case_id).update({
                "assigned_to": reviewer_id,
                "status": "assigned",
            })
        )

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        stream = self._collection(COLLECTION).where("status", "==", status).stream()
        results = await self._collect_stream(stream)
        return [data for _, data in results]
