"""Persistent idempotency store using Firestore.

Replaces the in-memory dict in resolve.py.
Stores idempotency keys with TTL for automatic cleanup (INV-001).

Supports both sync (InMemoryFirestore) and async (real AsyncClient) backends
via inspect.isawaitable().
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol


class IdempotencyRepository:
    """Tenant-scoped idempotency key store.

    Each key is stored with response, created_at, and expires_at (24h TTL).
    """

    DEFAULT_TTL_HOURS = 24

    def __init__(self, db: FirestoreClientProtocol, tenant_id: str) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._base_path = f"tenants/{tenant_id}/idempotency_keys"

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        """Get cached response for an idempotency key, if it exists and hasn't expired."""
        doc_ref = self._db.collection(self._base_path).document(key)
        doc = doc_ref.get()
        if inspect.isawaitable(doc):
            doc = await doc
        if doc is None:
            return None
        # Handle both in-memory (dict) and real Firestore (DocumentSnapshot)
        data = doc.to_dict() if hasattr(doc, "to_dict") else doc
        if data is None:
            return None

        # Check TTL
        expires_at = data.get("expires_at", "")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    result = self._db.collection(self._base_path).document(key).delete()
                    if inspect.isawaitable(result):
                        await result
                    return None
            except (ValueError, TypeError):
                pass

        return data.get("response")

    async def put(self, key: str, response: dict[str, Any]) -> None:
        """Store a response for an idempotency key."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.DEFAULT_TTL_HOURS)
        result = self._db.collection(self._base_path).document(key).set({
            "response": response,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        })
        if inspect.isawaitable(result):
            await result
