"""Public metadata storage — separate from tenant-scoped operational data.

Lifecycle: draft → approved → published → revoked.
Only published samples appear on public read endpoints.
Storage paths are under platform/, never tenants/.

Async-safe: all Firestore operations use inspect.isawaitable()
for dual sync/async backend support.
"""

from __future__ import annotations

import inspect
from typing import Any, Optional

from apps.api.src.public_metadata.models import (
    ManualApprovalStatus,
    PublicAuthoritySample,
    PublicMetadataDecision,
    SampleStatus,
)
from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol

SAMPLES_PATH = "pmc_public_samples"
DECISIONS_PATH = "pmc_public_decisions"

_VALID_TRANSITIONS: dict[str, set[str]] = {
    SampleStatus.DRAFT.value: {SampleStatus.APPROVED.value},
    SampleStatus.APPROVED.value: {SampleStatus.PUBLISHED.value, SampleStatus.REVOKED.value},
    SampleStatus.PUBLISHED.value: {SampleStatus.REVOKED.value},
    SampleStatus.REVOKED.value: set(),
}


async def _aw(result: Any) -> Any:
    """Await if coroutine, return as-is otherwise."""
    if inspect.isawaitable(result):
        return await result
    return result


async def _collect(stream: Any) -> list[tuple[str, dict[str, Any]]]:
    """Collect stream results from sync list or async iterator."""
    if isinstance(stream, list):
        return stream
    results = []
    async for doc in stream:
        data = doc.to_dict() if hasattr(doc, "to_dict") else doc
        doc_id = doc.id if hasattr(doc, "id") else ""
        results.append((doc_id, data))
    return results


class PublicMetadataStore:
    def __init__(self, db: FirestoreClientProtocol) -> None:
        self._db = db

    # --- Samples ---

    async def save_sample(self, sample: PublicAuthoritySample) -> None:
        await _aw(self._db.collection(SAMPLES_PATH).document(sample.public_sample_id).set(sample.model_dump()))

    async def get_sample(self, sample_id: str) -> Optional[dict[str, Any]]:
        doc = await _aw(self._db.collection(SAMPLES_PATH).document(sample_id).get())
        if doc is None:
            return None
        return doc.to_dict() if hasattr(doc, "to_dict") else doc

    async def list_published(self) -> list[dict[str, Any]]:
        """Return only published samples — the canonical public-read contract."""
        stream = self._db.collection(SAMPLES_PATH).where(
            "status", "==", SampleStatus.PUBLISHED.value
        ).stream()
        results = await _collect(stream)
        return [data for _, data in results]

    async def list_by_status(self, status: SampleStatus | None = None) -> list[dict[str, Any]]:
        if status is not None:
            stream = self._db.collection(SAMPLES_PATH).where("status", "==", status.value).stream()
        else:
            stream = self._db.collection(SAMPLES_PATH).stream()
        results = await _collect(stream)
        items = [data for _, data in results]
        items.sort(key=lambda d: d.get("emitted_at", ""), reverse=True)
        return items

    async def transition_sample(self, sample_id: str, new_status: SampleStatus) -> bool:
        current = await self.get_sample(sample_id)
        if current is None:
            return False
        if new_status.value not in _VALID_TRANSITIONS.get(current.get("status", ""), set()):
            return False
        await _aw(self._db.collection(SAMPLES_PATH).document(sample_id).update({"status": new_status.value}))
        return True

    async def approve_sample(self, sample_id: str) -> bool:
        return await self.transition_sample(sample_id, SampleStatus.APPROVED)

    async def publish_sample(self, sample_id: str) -> bool:
        return await self.transition_sample(sample_id, SampleStatus.PUBLISHED)

    async def revoke_sample(self, sample_id: str) -> bool:
        return await self.transition_sample(sample_id, SampleStatus.REVOKED)

    # --- Decisions ---

    async def save_decision(self, decision: PublicMetadataDecision) -> None:
        await _aw(self._db.collection(DECISIONS_PATH).document(decision.decision_id).set(decision.model_dump()))

    async def get_decision(self, decision_id: str) -> Optional[dict[str, Any]]:
        doc = await _aw(self._db.collection(DECISIONS_PATH).document(decision_id).get())
        if doc is None:
            return None
        return doc.to_dict() if hasattr(doc, "to_dict") else doc

    async def approve_decision(self, decision_id: str) -> bool:
        doc = await self.get_decision(decision_id)
        if doc is None:
            return False
        await _aw(self._db.collection(DECISIONS_PATH).document(decision_id).update({
            "manual_approval_status": ManualApprovalStatus.APPROVED.value,
        }))
        return True
