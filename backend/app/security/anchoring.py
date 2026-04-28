"""
================================================================================
INTELLIGENT ANALYST - EXTERNAL ANCHORING MODULE (Phase 3)
================================================================================

Writes batch root hashes to an external GCS bucket for tamper resistance.
The anchor record contains enough information to verify the batch independently.

Anchor path: anchors/<tenant_id_hash>/<batch_id>.json

The backend has objectCreator permission only - no delete or overwrite.
Once written, anchors are immutable.

================================================================================
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

# GCS client - lazy loaded
_gcs_client = None
_gcs_available = False

try:
    from google.cloud import storage
    _gcs_available = True
except ImportError:
    _gcs_available = False
    print("[Anchoring] google-cloud-storage not available", flush=True)


# Configuration
ANCHORING_ENABLED = os.getenv("ANCHORING_ENABLED", "false").lower() == "true"
ANCHOR_BUCKET = os.getenv("ANCHOR_BUCKET", "")


def _get_gcs_client():
    """Lazy-load GCS client."""
    global _gcs_client
    if _gcs_client is None and _gcs_available:
        _gcs_client = storage.Client()
    return _gcs_client


def _hash_tenant_id(tenant_id: str) -> str:
    """Hash tenant_id for path construction (privacy)."""
    if not tenant_id:
        return "unknown"
    return hashlib.sha256(tenant_id.encode()).hexdigest()[:16]


def build_anchor_record(
    batch_id: str,
    tenant_id: str,
    batch_root_hash: str,
    code_version: str,
    sbom_hash: str,
    chain_length: int,
    signing_key_id: str = None,  # Day 5: tenant-scoped signing key
) -> Dict[str, Any]:
    """
    Build anchor record for external storage.
    """
    return {
        "batch_id": batch_id,
        "tenant_id_hash": _hash_tenant_id(tenant_id),
        "batch_root_hash": batch_root_hash,
        "hash_algo": "SHA256",
        "chain_length": chain_length,
        "code_version": code_version,
        "sbom_hash": sbom_hash,
        "signing_key_id": signing_key_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "anchor_version": "1.0.0",
    }


def write_anchor_to_gcs(
    batch_id: str,
    tenant_id: str,
    anchor_record: Dict[str, Any]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Write anchor record to GCS.

    Returns:
        (success, anchor_path, error_message)
    """
    if not ANCHORING_ENABLED:
        return False, None, "anchoring_disabled"

    if not _gcs_available:
        return False, None, "gcs_not_available"

    if not ANCHOR_BUCKET:
        return False, None, "anchor_bucket_not_configured"

    client = _get_gcs_client()
    if not client:
        return False, None, "gcs_client_init_failed"

    try:
        bucket = client.bucket(ANCHOR_BUCKET)
        tenant_hash = _hash_tenant_id(tenant_id)
        anchor_path = f"anchors/{tenant_hash}/{batch_id}.json"

        blob = bucket.blob(anchor_path)

        # Write anchor record
        anchor_json = json.dumps(anchor_record, indent=2, sort_keys=True)
        blob.upload_from_string(
            anchor_json,
            content_type="application/json"
        )

        print(f"[Anchoring] Wrote anchor for {batch_id} to gs://{ANCHOR_BUCKET}/{anchor_path}", flush=True)
        return True, f"gs://{ANCHOR_BUCKET}/{anchor_path}", None

    except Exception as e:
        error_msg = f"gcs_write_error: {str(e)}"
        print(f"[Anchoring] Error: {error_msg}", flush=True)
        return False, None, error_msg


def read_anchor_from_gcs(
    batch_id: str,
    tenant_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Read anchor record from GCS for verification.

    Returns:
        (anchor_record, error_message)
    """
    if not _gcs_available:
        return None, "gcs_not_available"

    if not ANCHOR_BUCKET:
        return None, "anchor_bucket_not_configured"

    client = _get_gcs_client()
    if not client:
        return None, "gcs_client_init_failed"

    try:
        bucket = client.bucket(ANCHOR_BUCKET)
        tenant_hash = _hash_tenant_id(tenant_id)
        anchor_path = f"anchors/{tenant_hash}/{batch_id}.json"

        blob = bucket.blob(anchor_path)

        if not blob.exists():
            return None, "anchor_not_found"

        anchor_json = blob.download_as_string()
        anchor_record = json.loads(anchor_json)

        return anchor_record, None

    except Exception as e:
        return None, f"gcs_read_error: {str(e)}"


def verify_anchor(
    batch_id: str,
    tenant_id: str,
    computed_root_hash: str
) -> Dict[str, Any]:
    """
    Verify anchor integrity.

    Fetches anchor from GCS and compares batch_root_hash.
    """
    anchor_record, error = read_anchor_from_gcs(batch_id, tenant_id)

    if error:
        return {
            "verified": False,
            "error": error,
            "anchor_found": False,
        }

    stored_hash = anchor_record.get("batch_root_hash")
    matches = stored_hash == computed_root_hash

    return {
        "verified": matches,
        "error": None if matches else "root_hash_mismatch",
        "anchor_found": True,
        "anchor_path": f"gs://{ANCHOR_BUCKET}/anchors/{_hash_tenant_id(tenant_id)}/{batch_id}.json",
        "stored_hash": stored_hash,
        "computed_hash": computed_root_hash,
        "anchored_at": anchor_record.get("created_at_utc"),
    }


def get_anchoring_status() -> Dict[str, Any]:
    """Get anchoring status for /health endpoint."""
    return {
        "enabled": ANCHORING_ENABLED,
        "gcs_available": _gcs_available,
        "bucket": ANCHOR_BUCKET if ANCHORING_ENABLED else None,
    }
