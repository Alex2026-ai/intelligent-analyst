"""Storage-specific exceptions."""

from __future__ import annotations


class StorageError(Exception):
    """Base exception for storage operations."""


class TenantMismatchError(StorageError):
    """Raised when a document's tenant doesn't match the repository's tenant scope."""

    def __init__(self, expected: str, actual: str, resource_id: str) -> None:
        super().__init__(
            f"Tenant mismatch: expected '{expected}', got '{actual}' on resource '{resource_id}'"
        )
        self.expected_tenant = expected
        self.actual_tenant = actual
        self.resource_id = resource_id


class SchemaVersionError(StorageError):
    """Raised when a document's schema version doesn't match expected."""

    def __init__(self, collection: str, expected: int, actual: int | None) -> None:
        super().__init__(
            f"Schema version mismatch in '{collection}': expected {expected}, got {actual}"
        )
        self.collection = collection
        self.expected_version = expected
        self.actual_version = actual


class DocumentNotFoundError(StorageError):
    """Raised when a requested document doesn't exist."""

    def __init__(self, collection: str, doc_id: str) -> None:
        super().__init__(f"Document not found: {collection}/{doc_id}")
        self.collection = collection
        self.doc_id = doc_id
