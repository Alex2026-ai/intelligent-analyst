"""
Receipt writer for ia-attestation/v1.

Writes the canonical receipt bundle to GCS with idempotency guarantees:
- Deterministic paths (same batch → same GCS objects)
- First-write protection via ifGenerationMatch=0
- Hash verification on existing objects (skip duplicate writes)
- Firestore pointer written only after all GCS objects succeed

This module does NOT sign the manifest — signing is the caller's responsibility.
"""

import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.security.iavp import jcs_canonicalize
from app.attestation.receipt_paths import (
    get_receipt_bucket,
    manifest_path,
    signature_path,
    metadata_path,
    deterministic_receipt_id,
)

# GCS client (lazy-loaded, same pattern as anchoring.py)
_gcs_client = None
_gcs_available = False

try:
    from google.cloud import storage
    from google.api_core import exceptions as gcs_exceptions
    _gcs_available = True
except ImportError:
    storage = None
    gcs_exceptions = None
    _gcs_available = False


def _get_gcs_client():
    """Lazy-load GCS client (default service account credentials)."""
    global _gcs_client
    if _gcs_client is None and _gcs_available:
        _gcs_client = storage.Client()
    return _gcs_client


def _write_blob_idempotent(
    bucket_name: str,
    object_path: str,
    data: bytes,
    content_type: str,
    expected_hash: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Write a blob to GCS with first-write protection.

    If the object already exists:
    - Compute SHA-256 of existing object
    - If it matches expected_hash → skip (idempotent success)
    - If mismatch → raise (corruption detected)

    Returns:
        (wrote_new, status_message)
        - wrote_new=True if a new object was created
        - wrote_new=False if existing object matched (idempotent skip)

    Raises:
        RuntimeError: If existing object has wrong hash (corruption).
        Exception: On GCS write failure.
    """
    client = _get_gcs_client()
    if not client:
        raise RuntimeError("GCS client not available")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)

    # Try first-write with ifGenerationMatch=0 (object must not exist)
    try:
        blob.upload_from_string(
            data,
            content_type=content_type,
            if_generation_match=0,
        )
        return True, "created"
    except Exception as e:
        # Check if this is a "precondition failed" (object already exists)
        err_str = str(e)
        is_precondition = False
        if gcs_exceptions and isinstance(e, gcs_exceptions.PreconditionFailed):
            is_precondition = True
        elif "412" in err_str or "conditionNotMet" in err_str:
            is_precondition = True

        if not is_precondition:
            raise  # Unexpected error

    # Object exists — verify hash
    if expected_hash:
        blob.reload()
        existing_data = blob.download_as_bytes()
        existing_hash = hashlib.sha256(existing_data).hexdigest().lower()

        if existing_hash == expected_hash:
            return False, "idempotent_skip"
        else:
            raise RuntimeError(
                f"Receipt corruption: {object_path} exists with hash "
                f"{existing_hash[:16]}... but expected {expected_hash[:16]}..."
            )

    # No expected_hash provided, assume idempotent
    return False, "exists_no_verify"


def write_receipt_bundle(
    manifest: Dict[str, Any],
    signature_bytes: bytes,
    tenant_scope: str,
    receipt_id: str,
    batch_id: str,
    environment: str,
) -> Dict[str, Any]:
    """
    Write the full receipt bundle to GCS.

    Order:
    1. manifest.json (JCS canonical bytes)
    2. signature.der (raw ECDSA signature)
    3. receipt_metadata.json (lightweight metadata, no PII)

    Returns:
        Dict with write results for each object.

    Raises:
        RuntimeError: If GCS is unavailable or corruption detected.
        ValueError: If RECEIPT_BUCKET not configured.
    """
    bucket_name = get_receipt_bucket()
    timings = {}
    results = {}

    # 1. manifest.json — JCS canonical bytes
    manifest_bytes = jcs_canonicalize(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest().lower()
    m_path = manifest_path(tenant_scope, receipt_id)

    t0 = time.time()
    wrote, status = _write_blob_idempotent(
        bucket_name, m_path, manifest_bytes,
        content_type="application/json",
        expected_hash=manifest_hash,
    )
    timings["manifest_ms"] = round((time.time() - t0) * 1000, 1)
    results["manifest"] = {"path": m_path, "wrote": wrote, "status": status}

    # 2. signature.der — raw signature bytes
    sig_hash = hashlib.sha256(signature_bytes).hexdigest().lower()
    s_path = signature_path(tenant_scope, receipt_id)

    t0 = time.time()
    wrote, status = _write_blob_idempotent(
        bucket_name, s_path, signature_bytes,
        content_type="application/octet-stream",
        expected_hash=sig_hash,
    )
    timings["signature_ms"] = round((time.time() - t0) * 1000, 1)
    results["signature"] = {"path": s_path, "wrote": wrote, "status": status}

    # 3. receipt_metadata.json — lightweight, no PII, no raw tenant_id
    metadata = {
        "receipt_id": receipt_id,
        "batch_id": batch_id,
        "protocol_version": manifest.get("protocol_version"),
        "environment": environment,
        "manifest_hash": manifest_hash,
        "signature_hash": sig_hash,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    metadata_bytes = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")
    metadata_hash = hashlib.sha256(metadata_bytes).hexdigest().lower()
    md_path = metadata_path(tenant_scope, receipt_id)

    t0 = time.time()
    wrote, status = _write_blob_idempotent(
        bucket_name, md_path, metadata_bytes,
        content_type="application/json",
        expected_hash=metadata_hash,
    )
    timings["metadata_ms"] = round((time.time() - t0) * 1000, 1)
    results["metadata"] = {"path": md_path, "wrote": wrote, "status": status}

    return {
        "bucket": bucket_name,
        "receipt_id": receipt_id,
        "manifest_hash": manifest_hash,
        "results": results,
        "timings": timings,
        "gcs_prefix": f"gs://{bucket_name}/{manifest_path(tenant_scope, receipt_id).rsplit('/', 1)[0]}",
    }


def build_firestore_receipt_pointer(
    receipt_id: str,
    gcs_prefix: str,
) -> Dict[str, str]:
    """
    Build the lightweight Firestore receipt pointer.

    This is the ONLY receipt data stored in the batch doc.
    The full manifest and signature live in GCS.
    """
    return {
        "id": receipt_id,
        "gcs_path": gcs_prefix,
        "version": "ia-attestation/v1",
        "finalized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
