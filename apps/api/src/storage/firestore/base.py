"""Base repository with tenant scoping enforcement.

Every query is automatically scoped to the tenant — no way to accidentally
query across tenants (INV-005).

Provides async helpers for dual sync/async backend support via
inspect.isawaitable() and async iteration detection.

Deep instrumentation: every _await_if_needed() and _collect_stream() call
creates a child span visible in Cloud Trace waterfall diagrams.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from apps.api.src.storage.exceptions import DocumentNotFoundError, TenantMismatchError
from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol

CURRENT_SCHEMA_VERSION: int = 1

logger = logging.getLogger(__name__)


def _get_tracer():
    """Lazy tracer acquisition — returns NoOpTracer if OTel not initialized."""
    try:
        from opentelemetry import trace
        return trace.get_tracer("ia.storage.firestore")
    except ImportError:
        return None


class BaseRepository:
    """Base class for tenant-scoped Firestore repositories.

    tenant_id is set at construction (from auth middleware) and used
    for every operation. No per-query tenant parameter exists.

    Supports both sync (InMemoryFirestore) and async (real AsyncClient)
    backends via _await_if_needed() and _collect_stream().
    """

    def __init__(self, db: FirestoreClientProtocol, tenant_id: str) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._base_path = f"tenants/{tenant_id}"

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def _collection(self, name: str):
        """Returns tenant-scoped collection reference."""
        return self._db.collection(f"{self._base_path}/{name}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_id(self) -> str:
        return str(uuid.uuid4())

    def _with_schema_version(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add _schema_version to document data."""
        data["_schema_version"] = CURRENT_SCHEMA_VERSION
        return data

    @staticmethod
    async def _await_if_needed(result: Any, span_name: str = "firestore.operation") -> Any:
        """Await result if it's a coroutine, otherwise return as-is.

        Supports dual sync (InMemory) / async (real Firestore) backends.
        Creates a child span for every Firestore operation.
        """
        tracer = _get_tracer()
        if tracer is not None:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("db.system", "firestore")
                if inspect.isawaitable(result):
                    return await result
                return result
        else:
            if inspect.isawaitable(result):
                return await result
            return result

    @staticmethod
    async def _collect_stream(
        stream_result: Any, span_name: str = "firestore.stream"
    ) -> list[tuple[str, dict[str, Any]]]:
        """Collect results from a stream, handling both sync lists and async iterators.

        InMemoryFirestore.stream() returns list[tuple[str, dict]].
        AsyncClient .stream() returns an AsyncIterator of DocumentSnapshot.
        Creates a child span capturing document count.
        """
        tracer = _get_tracer()

        if tracer is not None:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("db.system", "firestore")
                # Sync backend returns a list directly
                if isinstance(stream_result, list):
                    span.set_attribute("db.result_count", len(stream_result))
                    return stream_result

                # Async backend returns an AsyncIterator of DocumentSnapshot
                results = []
                async for doc in stream_result:
                    data = doc.to_dict() if hasattr(doc, "to_dict") else doc
                    doc_id = doc.id if hasattr(doc, "id") else ""
                    results.append((doc_id, data))
                span.set_attribute("db.result_count", len(results))
                return results
        else:
            # No tracer — original behavior
            if isinstance(stream_result, list):
                return stream_result
            results = []
            async for doc in stream_result:
                data = doc.to_dict() if hasattr(doc, "to_dict") else doc
                doc_id = doc.id if hasattr(doc, "id") else ""
                results.append((doc_id, data))
            return results
