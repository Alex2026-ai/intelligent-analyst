"""
Receipt path builder for ia-attestation/v1.

Canonical GCS layout:
    gs://ia-{env}-receipts-{region}/receipts/{tenant_scope}/{receipt_id}/
        manifest.json
        signature.der
        receipt_metadata.json

Paths are deterministic: same inputs → same paths → idempotent writes.
"""

import hashlib
import os
from typing import Optional


def get_receipt_bucket() -> str:
    """
    Resolve the receipts GCS bucket from environment.

    Pattern: RECEIPT_BUCKET env var.
    Fail-closed: raises ValueError if not configured.
    """
    bucket = os.getenv("RECEIPT_BUCKET", "")
    if not bucket:
        raise ValueError("RECEIPT_BUCKET environment variable is required")
    return bucket


def build_receipt_prefix(tenant_scope: str, receipt_id: str) -> str:
    """
    Build the GCS prefix for a receipt bundle.

    Returns:
        Path prefix (no leading slash): "receipts/{tenant_scope}/{receipt_id}"
    """
    if not tenant_scope or len(tenant_scope) != 16:
        raise ValueError(f"tenant_scope must be 16-char hex, got: {tenant_scope!r}")
    if not receipt_id:
        raise ValueError("receipt_id is required")
    return f"receipts/{tenant_scope}/{receipt_id}"


def manifest_path(tenant_scope: str, receipt_id: str) -> str:
    """GCS object path for manifest.json."""
    return f"{build_receipt_prefix(tenant_scope, receipt_id)}/manifest.json"


def signature_path(tenant_scope: str, receipt_id: str) -> str:
    """GCS object path for signature.der."""
    return f"{build_receipt_prefix(tenant_scope, receipt_id)}/signature.der"


def metadata_path(tenant_scope: str, receipt_id: str) -> str:
    """GCS object path for receipt_metadata.json."""
    return f"{build_receipt_prefix(tenant_scope, receipt_id)}/receipt_metadata.json"


def deterministic_receipt_id(batch_id: str, root_hash: str) -> str:
    """
    Compute a deterministic receipt_id from batch_id + root_hash.

    This ensures retry-safe behavior: same batch with same root hash
    always produces the same receipt_id → same GCS path → idempotent.

    Returns:
        UUID-formatted string derived from SHA-256.
    """
    if not batch_id or not root_hash:
        raise ValueError("batch_id and root_hash are required for deterministic receipt_id")
    digest = hashlib.sha256(f"{batch_id}:{root_hash}".encode("utf-8")).hexdigest()
    # Format as UUID: 8-4-4-4-12
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
