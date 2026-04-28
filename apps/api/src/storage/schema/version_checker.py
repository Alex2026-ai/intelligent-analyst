"""Schema version checker — startup validation.

Samples documents from each collection and verifies _schema_version.
Mismatch blocks service startup (fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.api.src.storage.exceptions import SchemaVersionError
from apps.api.src.storage.firestore.protocol import FirestoreClientProtocol

EXPECTED_VERSIONS: dict[str, int] = {
    "resolutions": 1,
    "evidence_chains": 1,
    "review_cases": 1,
    "exports": 1,
    "audit_log": 1,
    "config": 1,
}


@dataclass
class SchemaCheckResult:
    """Result of schema version validation."""

    passed: bool = True
    mismatches: list[dict[str, Any]] = field(default_factory=list)


def check_schema_versions(
    db: FirestoreClientProtocol,
    tenant_id: str,
    expected: dict[str, int] | None = None,
) -> SchemaCheckResult:
    """Verify schema versions of sampled documents.

    Samples up to 10 documents from each collection and checks
    their _schema_version against expected values.

    Args:
        db: Firestore client.
        tenant_id: Tenant to check.
        expected: Expected schema versions per collection.

    Returns:
        SchemaCheckResult with pass/fail and mismatch details.
    """
    expected = expected or EXPECTED_VERSIONS
    result = SchemaCheckResult()

    for collection_name, expected_version in expected.items():
        collection = db.collection(f"tenants/{tenant_id}/{collection_name}")
        docs = collection.limit(10).stream()

        for doc_id, data in docs:
            actual = data.get("_schema_version")
            if actual != expected_version:
                result.passed = False
                result.mismatches.append({
                    "collection": collection_name,
                    "doc_id": doc_id,
                    "expected": expected_version,
                    "actual": actual,
                })

    return result
