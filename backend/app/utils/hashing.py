"""
Hashing helpers for Attestation Manifest v1.

Reuses the existing JCS implementation from app.security.iavp.
Does NOT duplicate the canonicalizer.
"""

import hashlib
import hmac
import os
from typing import Any, Dict, List, Optional

from app.security.iavp import (
    jcs_canonicalize,
    jcs_sha256,
    sort_records_stable_order,
)


def compute_dataset_hash_v1(records: List[Dict[str, Any]]) -> str:
    """
    Compute dataset hash per ia-attestation/v1 spec §1.5.

    dataset_hash = SHA256( JCS( array_of_original_strings_in_STABLE_INPUT_ORDER_V2 ) )

    Args:
        records: List of record dicts, each with an 'original' field.

    Returns:
        Lowercase 64-char hex SHA-256 digest.
    """
    if not records:
        return hashlib.sha256(jcs_canonicalize([])).hexdigest().lower()

    sorted_records, _ = sort_records_stable_order(records)
    originals = [str(r.get("original", "")) for r in sorted_records]
    canonical_bytes = jcs_canonicalize(originals)
    return hashlib.sha256(canonical_bytes).hexdigest().lower()


def compute_tenant_scope(
    tenant_id: str,
    scope_key: Optional[bytes] = None,
) -> str:
    """
    Compute pseudonymous tenant scope per ia-attestation/v1 spec §1.6.

    tenant_scope = HMAC-SHA256( key=scope_key, msg=tenant_id )[:16]

    Args:
        tenant_id: Internal tenant identifier.
        scope_key: 32-byte HMAC key. If None, reads from HMAC_SCOPE_KEY env var.

    Returns:
        16-char lowercase hex string.

    Raises:
        ValueError: If no scope_key provided and HMAC_SCOPE_KEY env var is missing.
    """
    if scope_key is None:
        key_hex = os.environ.get("HMAC_SCOPE_KEY")
        if not key_hex:
            raise ValueError(
                "HMAC_SCOPE_KEY environment variable is required for tenant_scope computation"
            )
        scope_key = bytes.fromhex(key_hex)

    digest = hmac.new(scope_key, tenant_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16].lower()


def compute_source_blob_hash(blob_bytes: bytes) -> str:
    """
    Compute SHA-256 of raw uploaded file bytes.

    Args:
        blob_bytes: Raw bytes of the uploaded file.

    Returns:
        Lowercase 64-char hex SHA-256 digest.
    """
    return hashlib.sha256(blob_bytes).hexdigest().lower()
