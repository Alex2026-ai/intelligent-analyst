"""Data-layer tenant partition guard.

Every Firestore query goes through get_tenant_partition() which injects
the tenant_id scope. This makes cross-tenant access structurally impossible.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol


class TenantPartition:
    """Tenant-scoped Firestore access. All queries are automatically partitioned."""

    def __init__(self, db: FirestoreClientProtocol, tenant_id: str) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._prefix = f"tenants/{tenant_id}"

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def partition_path(self) -> str:
        return self._prefix

    def collection(self, name: str) -> Any:
        """Get a tenant-scoped collection. Path is always prefixed."""
        return self._db.collection(f"{self._prefix}/{name}")

    def resolutions(self) -> Any:
        return self.collection("resolutions")

    def evidence_chains(self) -> Any:
        return self.collection("evidence_chains")

    def review_cases(self) -> Any:
        return self.collection("review_cases")

    def exports(self) -> Any:
        return self.collection("exports")

    def audit_log(self) -> Any:
        return self.collection("audit_log")

    def config(self) -> Any:
        return self.collection("config")


def get_tenant_partition(
    db: FirestoreClientProtocol, tenant_id: str
) -> TenantPartition:
    """Factory for tenant-scoped database access.

    Usage in route handlers:
        partition = get_tenant_partition(request.app.state.firestore_client, auth.tenant_id)
        docs = partition.resolutions().stream()
    """
    return TenantPartition(db, tenant_id)
