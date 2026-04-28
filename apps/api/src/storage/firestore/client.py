"""Firestore client abstraction.

Provides an in-memory implementation for testing and a protocol
for real Firestore integration.
"""

from __future__ import annotations

import copy
from typing import Any, Optional


class InMemoryFirestore:
    """In-memory Firestore-like client for testing.

    Supports collection/document paths with tenant scoping.
    Thread-safe for single-threaded test use.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def collection(self, path: str) -> "_Collection":
        return _Collection(self._data, path)

    def clear(self) -> None:
        """Clear all data (for test cleanup)."""
        self._data.clear()


class _Collection:
    """In-memory collection reference."""

    def __init__(self, store: dict[str, dict[str, Any]], path: str) -> None:
        self._store = store
        self._path = path

    def document(self, doc_id: str) -> "_Document":
        return _Document(self._store, f"{self._path}/{doc_id}")

    def add(self, data: dict[str, Any], doc_id: str) -> str:
        """Add a document to the collection."""
        key = f"{self._path}/{doc_id}"
        self._store[key] = copy.deepcopy(data)
        return doc_id

    def where(self, field: str, op: str, value: Any) -> "_Query":
        return _Query(self._store, self._path, [(field, op, value)])

    def stream(self) -> list[tuple[str, dict[str, Any]]]:
        """Stream all documents in this collection."""
        prefix = self._path + "/"
        results = []
        for key, data in self._store.items():
            if key.startswith(prefix) and key.count("/") == prefix.count("/"):
                doc_id = key[len(prefix):]
                if "/" not in doc_id:  # Only direct children
                    results.append((doc_id, copy.deepcopy(data)))
        return results

    def limit(self, n: int) -> "_Query":
        return _Query(self._store, self._path, [], limit=n)


class _Document:
    """In-memory document reference."""

    def __init__(self, store: dict[str, dict[str, Any]], path: str) -> None:
        self._store = store
        self._path = path

    def set(self, data: dict[str, Any]) -> None:
        self._store[self._path] = copy.deepcopy(data)

    def get(self) -> Optional[dict[str, Any]]:
        data = self._store.get(self._path)
        return copy.deepcopy(data) if data is not None else None

    def update(self, data: dict[str, Any]) -> None:
        existing = self._store.get(self._path)
        if existing is None:
            raise KeyError(f"Document not found: {self._path}")
        existing.update(copy.deepcopy(data))

    def collection(self, path: str) -> "_Collection":
        """Access a subcollection under this document."""
        return _Collection(self._store, f"{self._path}/{path}")

    def delete(self) -> None:
        self._store.pop(self._path, None)


class _Query:
    """In-memory query with filtering."""

    def __init__(
        self,
        store: dict[str, dict[str, Any]],
        collection_path: str,
        filters: list[tuple[str, str, Any]],
        limit: int | None = None,
    ) -> None:
        self._store = store
        self._collection_path = collection_path
        self._filters = filters
        self._limit = limit

    def where(self, field: str, op: str, value: Any) -> "_Query":
        return _Query(
            self._store,
            self._collection_path,
            self._filters + [(field, op, value)],
            self._limit,
        )

    def stream(self) -> list[tuple[str, dict[str, Any]]]:
        prefix = self._collection_path + "/"
        results = []
        for key, data in self._store.items():
            if not key.startswith(prefix):
                continue
            doc_id = key[len(prefix):]
            if "/" in doc_id:
                continue
            if self._matches(data):
                results.append((doc_id, copy.deepcopy(data)))
        if self._limit:
            results = results[: self._limit]
        return results

    def _matches(self, data: dict[str, Any]) -> bool:
        for field, op, value in self._filters:
            actual = data.get(field)
            if op == "==" and actual != value:
                return False
            if op == "!=" and actual == value:
                return False
            if op == "<" and (actual is None or actual >= value):
                return False
            if op == ">" and (actual is None or actual <= value):
                return False
        return True
